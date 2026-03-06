// flows/static/js/builder_render.js
// Exposes FlowBuilder.init/destroy to bootstrap the builder on demand.
/* global window, document, bootstrap */

(function (global) {
  const managerFactory = global.FlowBuilderManagerFactory;

  if (!managerFactory) {
    console.warn('[FlowBuilder]', 'Missing FlowBuilderManagerFactory. Flow builder cannot bootstrap.');
    return;
  }

  let activeInstance = null;

  const FlowBuilder = {
    init(rootElement, flowId) {
      FlowBuilder.destroy();
      if (!rootElement) {
        console.warn('[FlowBuilder]', 'init called without a root element');
        return;
      }
      activeInstance = createInstance(rootElement, flowId);
    },
    destroy() {
      if (activeInstance) {
        activeInstance.destroy();
        activeInstance = null;
      }
    },
  };

  function createInstance(rootElement, flowId) {
    const cleanupCallbacks = [];
    global.__FLOW_BUILDER_ACTIVE__ = true;
    const addCleanup = (fn) => {
      if (typeof fn === 'function') {
        cleanupCallbacks.push(fn);
      }
    };

    const addListener = (target, eventName, handler, options) => {
      if (!target || typeof target.addEventListener !== 'function') {
        return;
      }
      target.addEventListener(eventName, handler, options);
      addCleanup(() => {
        target.removeEventListener(eventName, handler, options);
      });
    };

    const debugAttr = rootElement?.dataset?.debug;
    const stageAttr = rootElement?.dataset?.stage;
    const DEBUG = debugAttr === 'true' || debugAttr === '1' || global.__FLOW_BUILDER_DEBUG__ === true;
    const ACTIVE_STAGE = typeof stageAttr === 'string' && stageAttr ? stageAttr : null;

    const log = (...args) => {
      if (DEBUG) {
        console.log('[FlowBuilder][render]', ...args);
      }
    };

    const warn = (...args) => {
      if (DEBUG) {
        console.warn('[FlowBuilder][render]', ...args);
      }
    };

    const cloneValue = (value) => {
      if (value == null) return { nodes: [], edges: [] };
      try {
        return JSON.parse(JSON.stringify(value));
      } catch (error) {
        warn('Failed to clone value', error);
        return { nodes: [], edges: [] };
      }
    };

    const parseScriptPayload = (id) => {
      const el = document.getElementById(id);
      if (!el) return null;
      try {
        return JSON.parse(el.textContent || 'null');
      } catch (error) {
        warn('Failed to parse JSON payload', { id, error });
        return null;
      }
    };

    const initialGraph = (() => {
      if (global.__graph__ && typeof global.__graph__ === 'object') {
        return cloneValue(global.__graph__);
      }
      const parsed = parseScriptPayload('graph_json');
      if (parsed) return cloneValue(parsed);
      return { nodes: [], edges: [] };
    })();

    const definitions = parseScriptPayload('node_definitions_json') || global.__nodeDefinitions || {};
    const whatsappTemplatesUrl = rootElement?.dataset?.whatsappTemplatesUrl || '';
    const webhookCreateUrl = rootElement?.dataset?.webhookCreateUrl || '';
    const webhookListUrl = rootElement?.dataset?.webhookListUrl || '';
    const normaliseWebhookEntry = (entry) => {
      if (!entry || typeof entry !== 'object') {
        return { id: '', name: '', description: '', url: '', handler_path: '' };
      }
      return {
        id: String(entry.id ?? ''),
        name: entry.name || '',
        description: entry.description || '',
        url: entry.url || '',
        handler_path: entry.handler_path || '',
      };
    };
    const initialWebhooks = parseScriptPayload('available_webhooks_json') || [];
    let availableWebhooks = Array.isArray(initialWebhooks)
      ? initialWebhooks.map(normaliseWebhookEntry)
      : [];
    let whatsappTemplatesCache = null;
    let whatsappTemplatesError = null;
    let whatsappTemplatesRequest = null;

    const manager = managerFactory.create();
    manager.init({ initialGraph, initialDefinitions: definitions, debug: DEBUG, stage: ACTIVE_STAGE });
    if (ACTIVE_STAGE) {
      log('Active builder stage', ACTIVE_STAGE);
    }

    let zoom = 1;
    let panX = 0;
    let panY = 0;

    const stage = rootElement.querySelector('#stage');
    const canvasWrap = rootElement.querySelector('#canvasWrap');
    const canvas = rootElement.querySelector('#canvas');
    const edgesLayer = rootElement.querySelector('#edges-layer');

    if (!stage || !canvas || !edgesLayer || !canvasWrap) {
      warn('Missing stage/canvas/edges-layer/canvasWrap elements. Flow builder cannot render.');
      return {
        destroy() {
          manager.destroy();
        },
      };
    }

    const modalRegistry = {
      raw: document.getElementById('modal-raw'),
      agent: document.getElementById('modal-agent'),
      trigger_webhook: document.getElementById('modal-trigger-webhook'),
      branch: document.getElementById('modal-branch'),
      while: document.getElementById('modal-while'),
      tool_send_whatsapp_template: document.getElementById('modal-whatsapp-template'),
    };
    const edgeModalEl = document.getElementById('modal-edge');
    const webhookModalState = {
      select: null,
      details: null,
      nameWrap: null,
      customNameInput: null,
      updateNameVisibility: null,
      updateDetails: null,
    };

    const uid = () => 'n-' + Math.random().toString(36).slice(2, 9);
    const gridSnap = (value) => Math.round(value / 24) * 24;
    const clientToStage = (ev) => {
      const rect = canvasWrap.getBoundingClientRect();
      return {
        x: (ev.clientX - rect.left - panX) / zoom,
        y: (ev.clientY - rect.top - panY) / zoom,
      };
    };

    const rectCenterToStage = (rect) => {
      const wrapRect = canvasWrap.getBoundingClientRect();
      return {
        x: (rect.left + rect.width / 2 - wrapRect.left - panX) / zoom,
        y: (rect.top + rect.height / 2 - wrapRect.top - panY) / zoom,
      };
    };

    const computeCenteredPan = () => {
      const wrapRect = canvasWrap.getBoundingClientRect();
      const stageWidth = stage.offsetWidth * zoom;
      const stageHeight = stage.offsetHeight * zoom;
      const centeredX = (wrapRect.width - stageWidth) / 2;
      const centeredY = (wrapRect.height - stageHeight) / 2;
      return {
        x: Number.isFinite(centeredX) ? centeredX : 0,
        y: Number.isFinite(centeredY) ? centeredY : 0,
      };
    };

    const resetPanToCenter = () => {
      const { x, y } = computeCenteredPan();
      panX = x;
      panY = y;
    };

    const escapeHtml = (value) => {
      if (value == null) return '';
      return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    };

    const ensureArray = manager.ensureArray;
    const computePorts = manager.computePorts;
    const getDefinition = manager.getDefinition;
    const findNode = manager.findNode;

    const normaliseTemplate = (template) => ({
      id: template?.id ?? template?.name ?? '',
      name: template?.name ?? template?.id ?? '',
      language: template?.language || '',
      category: template?.category || '',
      status: template?.status || '',
      components: ensureArray(template?.components),
      placeholders: ensureArray(template?.placeholders),
      requirements: ensureArray(template?.requirements),
    });

    const getNodeIcon = (kind) => {
      const definition = getDefinition(kind);
      if (definition?.icon) return definition.icon;
      const fallback = {
        trigger_manual: 'hand-index',
        trigger_webhook: 'globe',
        trigger_signal: 'broadcast-pin',
        trigger_event: 'diagram-2',
        trigger_scheduled: 'alarm',
        trigger_process: 'cpu',
        agent: 'robot',
        tool_create_contact: 'person-plus',
        tool_create_ticket: 'ticket',
        tool_send_whatsapp: 'whatsapp',
        tool_send_whatsapp_template: 'chat-square-text',
        tool_send_email: 'envelope',
        tool_http_request: 'link-45deg',
        tool_update_candidate: 'person-badge',
        logic_branch: 'shuffle',
        logic_condition: 'diagram-3',
        logic_while: 'arrow-repeat',
        transform: 'sliders',
        output_function: 'code-slash',
        output_task: 'rocket-takeoff',
        output_event: 'broadcast',
        output_webhook_reply: 'reply',
        output_agent: 'emoji-smile',
      };
      return fallback[kind] || 'question-circle';
    };

    const findPortEl = (nodeId, side, portName) => {
      const selector = side === 'out'
        ? `[data-id="${nodeId}"] .ports.right .handle[data-port="${portName || 'out'}"]`
        : `[data-id="${nodeId}"] .ports.left .handle[data-port="${portName || 'in'}"]`;
      return canvas.querySelector(selector);
    };

    const applyOobHtml = (html) => {
      if (!html || typeof html !== 'string') return;
      const template = document.createElement('template');
      template.innerHTML = html.trim();
      template.content.querySelectorAll('[hx-swap-oob]').forEach((element) => {
        const targetId = element.id;
        const swapAttr = element.getAttribute('hx-swap-oob') || '';
        if (!targetId) return;
        const target = document.getElementById(targetId);
        if (!target) return;
        if (swapAttr.includes('beforeend')) {
          target.insertAdjacentHTML('beforeend', element.innerHTML);
        } else if (swapAttr.includes('innerHTML')) {
          target.innerHTML = element.innerHTML;
        } else {
          target.innerHTML = element.innerHTML;
        }
      });
    };

    const redrawEdges = () => {
      const defs = edgesLayer.querySelector('defs');
      edgesLayer.replaceChildren();
      if (defs) edgesLayer.appendChild(defs);
      for (const edge of manager.getEdges()) {
        drawEdge(edge);
      }
      highlightSelectedEdge();
    };

    const portTypeLabel = (port) => {
      const type = port?.schema?.type;
      if (!type) return '';
      return Array.isArray(type) ? type.join('/') : type;
    };

    const renderNodePort = (port) => {
      const type = portTypeLabel(port);
      const typeHtml = type ? `<span class="handle-type">(${escapeHtml(type)})</span>` : '';
      return `<div class="handle" data-port="${escapeHtml(port.name)}" data-description="${escapeHtml(port.description || '')}" data-schema-preview="${escapeHtml(port.schema_preview || '')}"><span class="handle-label">${escapeHtml(port.name)}${typeHtml}</span></div>`;
    };

    let selectedNodeId = null;
    let selectedEdgeId = null;

    const renderNode = (node) => {
      const ports = computePorts(node);
      const element = document.createElement('div');
      element.className = 'node flow-node position-relative';
      element.style.left = (node.x || 80) + 'px';
      element.style.top = (node.y || 80) + 'px';
      element.dataset.id = node.id;
      element.dataset.nodeId = node.id;
      if (node.kind) element.dataset.kind = node.kind;

      const inPortsHtml = ensureArray(ports.in).map(renderNodePort).join('');
      const outPortsHtml = ensureArray(ports.out).map(renderNodePort).join('');

      element.innerHTML = `
        <div class="node-header">
          <i class="bi bi-${getNodeIcon(node.kind)} me-2"></i>
          <span class="fw-semibold">${escapeHtml(node.name || node.kind)}</span>
          <button type="button" class="btn btn-light btn-xxs node-gear" title="Configure" data-node-id="${node.id}" data-node-kind="${node.kind}">
            <i class="bi bi-gear-fill"></i>
          </button>
        </div>
        <div class="node-body small">
          <div>id: <code>${escapeHtml(node.id)}</code></div>
          ${node.description ? `<div class="text-muted">${escapeHtml(node.description)}</div>` : ''}
        </div>
        ${ports.in?.length ? `<div class="ports left">${inPortsHtml}</div>` : ''}
        ${ports.out?.length ? `<div class="ports right">${outPortsHtml}</div>` : ''}
      `;

      const gearButton = element.querySelector('.node-gear');
      if (gearButton) {
        addListener(gearButton, 'click', (event) => {
          event.stopPropagation();
          openEditor(node);
        });
      }

      enableSelect(element);
      enableDrag(element);
      enableConnect(element);

      return element;
    };

    const render = () => {
      log('Rendering graph', {
        nodes: manager.getNodes().length,
        edges: manager.getEdges().length,
      });
      canvas.innerHTML = '';
      for (const node of manager.getNodes()) {
        canvas.appendChild(renderNode(node));
      }
      requestAnimationFrame(redrawEdges);
    };

    const drawEdge = (edge) => {
      const sourceNode = findNode(edge.source);
      const targetNode = findNode(edge.target);
      if (!sourceNode || !targetNode) return;

      const sourcePort = findPortEl(sourceNode.id, 'out', edge.source_port);
      const targetPort = findPortEl(targetNode.id, 'in', edge.target_port);
      if (!sourcePort || !targetPort) return;

      const sourceRect = sourcePort.getBoundingClientRect();
      const targetRect = targetPort.getBoundingClientRect();
      const { x: ax, y: ay } = rectCenterToStage(sourceRect);
      const { x: bx, y: by } = rectCenterToStage(targetRect);
      const dx = Math.max(60, Math.abs(bx - ax));
      const pathDefinition = `M ${ax} ${ay} C ${ax + dx / 2} ${ay}, ${bx - dx / 2} ${by}, ${bx} ${by}`;

      const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      group.setAttribute('data-edge-id', edge.id);

      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', pathDefinition);
      path.setAttribute('class', 'edge');
      path.setAttribute('data-edge-id', edge.id);
      if (selectedEdgeId === edge.id) {
        path.classList.add('selected');
      }

      addListener(path, 'click', (event) => {
        event.stopPropagation();
        selectedNodeId = null;
        document.querySelectorAll('.node').forEach((nodeEl) => nodeEl.classList.remove('selected'));
        selectedEdgeId = edge.id;
        highlightSelectedEdge();
        openEdgeInspector(edge);
      });

      const startHandle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      startHandle.setAttribute('class', 'edge-handle');
      startHandle.setAttribute('r', '6');
      startHandle.setAttribute('cx', ax);
      startHandle.setAttribute('cy', ay);

      const endHandle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      endHandle.setAttribute('class', 'edge-handle');
      endHandle.setAttribute('r', '6');
      endHandle.setAttribute('cx', bx);
      endHandle.setAttribute('cy', by);

      const startReconnect = (side, targetX, targetY) => {
        const tempPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        tempPath.setAttribute('class', 'temp-edge');
        edgesLayer.appendChild(tempPath);

        const onMove = (event) => {
          const point = clientToStage(event);
          const definition = side === 'source'
            ? `M ${point.x} ${point.y} C ${point.x + 30} ${point.y}, ${targetX - 30} ${targetY}, ${targetX} ${targetY}`
            : `M ${targetX} ${targetY} C ${targetX + 30} ${targetY}, ${point.x - 30} ${point.y}, ${point.x} ${point.y}`;
          tempPath.setAttribute('d', definition);
        };

        const onEnd = (event) => {
          window.removeEventListener('mousemove', onMove);
          window.removeEventListener('mouseup', onEnd);
          const under = document.elementFromPoint(event.clientX, event.clientY);
          if (side === 'source') {
            const outHandle = under?.closest?.('.ports.right .handle');
            if (outHandle) {
              const nodeEl = outHandle.closest('.node');
              edge.source = nodeEl.dataset.id;
              edge.source_port = outHandle.dataset.port || 'out';
              redrawEdges();
            }
          } else {
            const inHandle = under?.closest?.('.ports.left .handle');
            if (inHandle) {
              const nodeEl = inHandle.closest('.node');
              edge.target = nodeEl.dataset.id;
              edge.target_port = inHandle.dataset.port || 'in';
              redrawEdges();
            }
          }
          tempPath.remove();
        };

        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onEnd);
      };

      addListener(startHandle, 'mousedown', () => startReconnect('source', bx, by));
      addListener(endHandle, 'mousedown', () => startReconnect('target', ax, ay));

      group.appendChild(path);
      group.appendChild(startHandle);
      group.appendChild(endHandle);
      edgesLayer.appendChild(group);
    };

    const highlightSelectedEdge = () => {
      edgesLayer.querySelectorAll('.edge').forEach((edgeEl) => {
        if (edgeEl.getAttribute('data-edge-id') === selectedEdgeId) {
          edgeEl.classList.add('selected');
        } else {
          edgeEl.classList.remove('selected');
        }
      });
    };

    const edgeForm = edgeModalEl ? edgeModalEl.querySelector('#form-edge') : null;
    const edgeSourceSelect = edgeForm ? edgeForm.querySelector('select[name="source"]') : null;
    const edgeTargetSelect = edgeForm ? edgeForm.querySelector('select[name="target"]') : null;
    const edgeStatusEl = edgeModalEl ? edgeModalEl.querySelector('#edge-status') : null;
    const edgeSrcSchemaEl = edgeModalEl ? edgeModalEl.querySelector('#edge-src-schema') : null;
    const edgeDstSchemaEl = edgeModalEl ? edgeModalEl.querySelector('#edge-dst-schema') : null;
    const edgeDeleteBtn = edgeModalEl ? edgeModalEl.querySelector('#edge-delete') : null;
    let activeEdge = null;

    const closeEdgeInspector = () => {
      if (!edgeModalEl || typeof bootstrap === 'undefined') return;
      const instance = bootstrap.Modal.getInstance(edgeModalEl);
      if (instance) instance.hide();
      activeEdge = null;
    };

    const getPortInfo = (nodeId, side, portName) => {
      if (!nodeId || !portName) return null;
      const node = findNode(nodeId);
      if (!node) return null;
      const ports = computePorts(node);
      const entries = side === 'out' ? ensureArray(ports.out) : ensureArray(ports.in);
      const port = entries.find((item) => item.name === portName);
      return port ? { node, port } : null;
    };

    const renderSchemaText = (port) => {
      if (!port) return 'Schema not available';
      if (port.schema_preview) return port.schema_preview;
      if (port.schema) return JSON.stringify(port.schema, null, 2);
      return 'Schema not available';
    };

    const readSelectValue = (select) => {
      if (!select) return null;
      const value = select.value;
      if (!value || !value.includes('::')) return null;
      const [nodeId, portName] = value.split('::');
      return { nodeId, portName };
    };

    const populateEdgeSelect = (select, side, selectedNodeIdValue, selectedPortName) => {
      if (!select) return;
      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = side === 'out' ? 'Select source port' : 'Select target port';
      select.innerHTML = '';
      select.appendChild(placeholder);
      for (const node of manager.getNodes()) {
        const ports = computePorts(node);
        const entries = side === 'out' ? ensureArray(ports.out) : ensureArray(ports.in);
        for (const port of entries) {
          const option = document.createElement('option');
          option.value = `${node.id}::${port.name}`;
          const arrow = side === 'out' ? '▷' : '◁';
          option.textContent = `${node.name || node.kind} ${arrow} ${port.name}`;
          if (node.id === selectedNodeIdValue && port.name === selectedPortName) {
            option.selected = true;
          }
          select.appendChild(option);
        }
      }
      if (selectedNodeIdValue && selectedPortName) {
        select.value = `${selectedNodeIdValue}::${selectedPortName}`;
      }
    };

    const typeArray = (schema) => {
      if (!schema || !schema.type) return [];
      const raw = schema.type;
      return Array.isArray(raw) ? raw.map(String) : [String(raw)];
    };

    const describeEdgeStatus = (srcPort, dstPort) => {
      if (!srcPort || !dstPort) {
        return { text: 'Select both ports to compare schemas', cls: 'text-warning' };
      }
      if (!srcPort.schema && !dstPort.schema) {
        return { text: 'No schema metadata to compare', cls: 'text-muted' };
      }
      const srcTypes = typeArray(srcPort.schema);
      const dstTypes = typeArray(dstPort.schema);
      if (!srcTypes.length || !dstTypes.length) {
        return { text: 'Schema types are unspecified', cls: 'text-muted' };
      }
      const matches = srcTypes.some((type) => dstTypes.includes(type));
      if (matches) {
        return { text: `Compatible (${srcTypes.join('/')})`, cls: 'text-success' };
      }
      return { text: `${srcTypes.join('/')} → ${dstTypes.join('/')} mismatch`, cls: 'text-danger' };
    };

    const updateEdgeInspectorPreview = () => {
      if (!activeEdge) return;
      const sourceSelection = readSelectValue(edgeSourceSelect) || {
        nodeId: activeEdge.source,
        portName: activeEdge.source_port || 'out',
      };
      const targetSelection = readSelectValue(edgeTargetSelect) || {
        nodeId: activeEdge.target,
        portName: activeEdge.target_port || 'in',
      };
      const srcInfo = getPortInfo(sourceSelection?.nodeId, 'out', sourceSelection?.portName);
      const dstInfo = getPortInfo(targetSelection?.nodeId, 'in', targetSelection?.portName);

      if (edgeSrcSchemaEl) edgeSrcSchemaEl.textContent = renderSchemaText(srcInfo?.port);
      if (edgeDstSchemaEl) edgeDstSchemaEl.textContent = renderSchemaText(dstInfo?.port);
      if (edgeStatusEl) {
        const status = describeEdgeStatus(srcInfo?.port, dstInfo?.port);
        edgeStatusEl.textContent = status.text;
        edgeStatusEl.className = `mt-1 ${status.cls}`;
      }
    };

    const openEdgeInspector = (edge) => {
      if (!edgeModalEl || typeof bootstrap === 'undefined') return;
      activeEdge = edge;
      populateEdgeSelect(edgeSourceSelect, 'out', edge.source, edge.source_port || 'out');
      populateEdgeSelect(edgeTargetSelect, 'in', edge.target, edge.target_port || 'in');
      updateEdgeInspectorPreview();
      const instance = bootstrap.Modal.getOrCreateInstance(edgeModalEl);
      instance.show();
    };

    if (edgeForm) {
      addListener(edgeForm, 'change', () => updateEdgeInspectorPreview());
      addListener(edgeForm, 'submit', (event) => {
        event.preventDefault();
        if (!activeEdge) return;
        const sourceSelection = readSelectValue(edgeSourceSelect);
        const targetSelection = readSelectValue(edgeTargetSelect);
        if (!sourceSelection || !targetSelection) return;
        activeEdge.source = sourceSelection.nodeId;
        activeEdge.source_port = sourceSelection.portName;
        activeEdge.target = targetSelection.nodeId;
        activeEdge.target_port = targetSelection.portName;
        redrawEdges();
        updateEdgeInspectorPreview();
      });
    }

    if (edgeDeleteBtn) {
      addListener(edgeDeleteBtn, 'click', (event) => {
        event.preventDefault();
        if (!activeEdge) return;
        manager.removeEdge(activeEdge.id);
        selectedEdgeId = null;
        activeEdge = null;
        redrawEdges();
        closeEdgeInspector();
      });
    }

    const enableSelect = (element) => {
      addListener(element, 'click', () => {
        selectedEdgeId = null;
        activeEdge = null;
        highlightSelectedEdge();
        closeEdgeInspector();
        selectedNodeId = element.dataset.id;
        document.querySelectorAll('.node').forEach((nodeEl) => nodeEl.classList.remove('selected'));
        element.classList.add('selected');
      });

      addListener(element, 'dblclick', () => {
        const node = findNode(element.dataset.id);
        openEditor(node);
      });
    };

    const enableDrag = (element) => {
      let startX = 0;
      let startY = 0;
      let originX = 0;
      let originY = 0;
      let moving = false;

      const onMouseDown = (event) => {
        if (event.button !== 0) return;
        if (event.target.closest('.handle')) return;
        event.stopPropagation();
        event.preventDefault();
        moving = true;
        startX = event.clientX;
        startY = event.clientY;
        const node = findNode(element.dataset.id);
        originX = node.x || 0;
        originY = node.y || 0;
        element.classList.add('ghost');
      };

      const onMouseMove = (event) => {
        if (!moving) return;
        const deltaX = (event.clientX - startX) / zoom;
        const deltaY = (event.clientY - startY) / zoom;
        const node = findNode(element.dataset.id);
        node.x = gridSnap(originX + deltaX);
        node.y = gridSnap(originY + deltaY);
        element.style.left = node.x + 'px';
        element.style.top = node.y + 'px';
        redrawEdges();
      };

      const onMouseUp = () => {
        if (!moving) return;
        moving = false;
        element.classList.remove('ghost');
      };

      addListener(element, 'mousedown', onMouseDown);
      addListener(window, 'mousemove', onMouseMove);
      addListener(window, 'mouseup', onMouseUp);
    };

    const enableConnect = (element) => {
      element.querySelectorAll('.ports.right .handle').forEach((handle) => {
        addListener(handle, 'mousedown', (event) => {
          event.stopPropagation();
          const sourceNodeId = element.dataset.id;
          const sourcePort = handle.dataset.port || 'out';
          const tempPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
          tempPath.setAttribute('class', 'temp-edge');
          edgesLayer.appendChild(tempPath);

          const onMove = (moveEvent) => {
            const handleRect = handle.getBoundingClientRect();
            const { x: ax, y: ay } = rectCenterToStage(handleRect);
            const point = clientToStage(moveEvent);
            const dx = Math.max(60, Math.abs(point.x - ax));
            tempPath.setAttribute('d', `M ${ax} ${ay} C ${ax + dx / 2} ${ay}, ${point.x - dx / 2} ${point.y}, ${point.x} ${point.y}`);
          };

          const onEnd = (upEvent) => {
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup', onEnd);
            const under = document.elementFromPoint(upEvent.clientX, upEvent.clientY);
            const inHandle = under?.closest?.('.ports.left .handle');
            if (inHandle) {
              const destinationNodeId = inHandle.closest('.node').dataset.id;
              const destinationPort = inHandle.dataset.port || 'in';
              if (destinationNodeId !== sourceNodeId) {
                manager.addEdge({
                  id: 'e-' + Math.random().toString(36).slice(2, 8),
                  source: sourceNodeId,
                  source_port: sourcePort,
                  target: destinationNodeId,
                  target_port: destinationPort,
                });
                redrawEdges();
              }
            }
            tempPath.remove();
          };

          window.addEventListener('mousemove', onMove);
          window.addEventListener('mouseup', onEnd);
        });
      });
    };

    const deleteSelectedNode = () => {
      if (!selectedNodeId) return;
      attemptNodeRemoval(selectedNodeId);
    };

    const deleteSelectedEdge = () => {
      if (!selectedEdgeId) return;
      manager.removeEdge(selectedEdgeId);
      selectedEdgeId = null;
      activeEdge = null;
      redrawEdges();
      closeEdgeInspector();
    };

    addListener(window, 'keydown', (event) => {
      const targetIsInput = event.target.matches && event.target.matches('input, textarea');
      if ((event.key === 'Delete' || event.key === 'Backspace') && !targetIsInput) {
        if (selectedNodeId) {
          event.preventDefault();
          deleteSelectedNode();
        } else if (selectedEdgeId) {
          event.preventDefault();
          deleteSelectedEdge();
        }
      }
    });

    const applyTransform = () => {
      stage.style.transform = `translate(${panX}px, ${panY}px) scale(${zoom})`;
      redrawEdges();
    };

    if (canvasWrap) {
      let panning = false;
      let startX = 0;
      let startY = 0;
      let originX = 0;
      let originY = 0;

      const onMouseDown = (event) => {
        if (event.button !== 0) return;
        const interactiveTarget = event.target.closest('.node, .handle, .edge, .edge-handle, .zoom-controls');
        if (interactiveTarget) {
          return;
        }
        panning = true;
        startX = event.clientX;
        startY = event.clientY;
        originX = panX;
        originY = panY;
        canvasWrap.classList.add('panning');
        event.preventDefault();
      };

      const onMouseMove = (event) => {
        if (!panning) return;
        panX = originX + (event.clientX - startX);
        panY = originY + (event.clientY - startY);
        applyTransform();
      };

      const onMouseUp = () => {
        if (!panning) return;
        panning = false;
        canvasWrap.classList.remove('panning');
      };

      addListener(canvasWrap, 'mousedown', onMouseDown);
      addListener(window, 'mousemove', onMouseMove);
      addListener(window, 'mouseup', onMouseUp);
    }

    addListener(stage, 'click', (event) => {
      if (event.target.closest('.node') || event.target.closest('.handle')) return;
      selectedEdgeId = null;
      activeEdge = null;
      highlightSelectedEdge();
      closeEdgeInspector();
    });

    const zoomIn = document.getElementById('zoomIn');
    const zoomOut = document.getElementById('zoomOut');
    const zoomReset = document.getElementById('zoomReset');
    if (zoomIn) addListener(zoomIn, 'click', () => { zoom = Math.min(2.0, zoom + 0.1); applyTransform(); });
    if (zoomOut) addListener(zoomOut, 'click', () => { zoom = Math.max(0.4, zoom - 0.1); applyTransform(); });
    if (zoomReset) addListener(zoomReset, 'click', () => {
      zoom = 1;
      resetPanToCenter();
      applyTransform();
    });

    rootElement.querySelectorAll('.palette-item').forEach((item) => {
      addListener(item, 'dragstart', (event) => {
        event.dataTransfer.setData('text/plain', JSON.stringify({
          kind: item.dataset.kind,
          title: item.dataset.title,
        }));
      });
    });

    const allowDrop = (event) => {
      event.preventDefault();
      if (event.dataTransfer) {
        event.dataTransfer.dropEffect = 'copy';
      }
    };

    const handleDrop = (event) => {
      event.preventDefault();
      event.stopPropagation();
      const transfer = event.dataTransfer;
      if (!transfer) return;
      const payload = transfer.getData('text/plain');
      if (!payload) return;
      let data = null;
      try {
        data = JSON.parse(payload);
      } catch (error) {
        warn('Invalid drag payload', error);
        return;
      }
      if (!data.kind) return;
      const point = clientToStage(event);
      const definition = getDefinition(data.kind) || {};
      const node = {
        id: uid(),
        kind: data.kind,
        x: gridSnap(point.x),
        y: gridSnap(point.y),
        name: data.title || definition.title || data.kind,
        description: definition.description || '',
        config: manager.deepClone(definition.default_config) || {},
      };
      if (node.kind === 'logic_branch') {
        const config = node.config || {};
        if (!Array.isArray(config.rules) || !config.rules.length) {
          config.rules = [{ name: 'true' }, { name: 'false' }];
        }
        config.else = Boolean(config.else);
        node.config = config;
      }
      if (node.kind === 'logic_while' && (!node.config || Object.keys(node.config).length === 0)) {
        node.config = { expr: 'True' };
      }
      computePorts(node);
      manager.addNode(node);
      render();
    };

    const registerDropTarget = (target) => {
      if (!target) return;
      addListener(target, 'dragover', allowDrop);
      addListener(target, 'drop', handleDrop);
    };

    registerDropTarget(canvasWrap);
    registerDropTarget(stage);
    registerDropTarget(canvas);
    registerDropTarget(edgesLayer);

    const getModalForKind = (kind) => {
      if (!kind) return modalRegistry.raw;
      if (kind === 'agent') return modalRegistry.agent;
      if (kind === 'trigger_webhook') return modalRegistry.trigger_webhook;
      if (kind === 'logic_branch') return modalRegistry.branch;
      if (kind === 'logic_while') return modalRegistry.while;
      if (kind === 'tool_send_whatsapp_template') return modalRegistry.tool_send_whatsapp_template;
      return modalRegistry.raw;
    };

    const hideModal = (modal) => {
      if (!modal || typeof bootstrap === 'undefined') return;
      const instance = bootstrap.Modal.getInstance(modal);
      if (instance) instance.hide();
    };

    const renderToolsChips = (container, tools, onRemove) => {
      if (!container) return;
      container.innerHTML = '';
      tools.forEach((tool, index) => {
        const chip = document.createElement('span');
        chip.className = 'badge text-bg-light d-flex align-items-center gap-2';
        chip.innerHTML = `<span>${escapeHtml(tool)}</span><button class="btn btn-sm btn-link p-0" type="button"><i class="bi bi-x"></i></button>`;
        const removeBtn = chip.querySelector('button');
        removeBtn.addEventListener('click', (event) => {
          event.preventDefault();
          if (typeof onRemove === 'function') {
            onRemove(index);
          }
        });
        container.appendChild(chip);
      });
    };

    const attemptNodeRemoval = (nodeId) => {
      if (!nodeId) return false;
      const node = findNode(nodeId);
      if (!node) return false;
      const connectedEdges = manager.getEdges().filter((edge) => edge.source === nodeId || edge.target === nodeId);
      if (connectedEdges.length) {
        const plural = connectedEdges.length === 1 ? '' : 's';
        window.alert(`Disconnect node "${node.name || node.kind}" before deleting it. (${connectedEdges.length} connection${plural} remain)`);
        return false;
      }
      manager.removeNode(nodeId);
      selectedNodeId = null;
      render();
      return true;
    };

    const fetchWhatsAppTemplates = async (force = false) => {
      if (!whatsappTemplatesUrl) {
        whatsappTemplatesCache = [];
        whatsappTemplatesError = 'WhatsApp template API is not configured for this flow.';
        return [];
      }
      if (whatsappTemplatesCache && !force) {
        return whatsappTemplatesCache;
      }
      if (whatsappTemplatesRequest && !force) {
        return whatsappTemplatesRequest;
      }
      const request = fetch(whatsappTemplatesUrl, {
        method: 'GET',
        headers: {
          Accept: 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'same-origin',
      })
        .then(async (response) => {
          if (!response.ok) {
            throw new Error(`Failed to load templates (${response.status})`);
          }
          const data = await response.json();
          whatsappTemplatesError = data?.error || null;
          const templates = Array.isArray(data?.templates) ? data.templates : [];
          whatsappTemplatesCache = templates.map((template) => normaliseTemplate(template));
          return whatsappTemplatesCache;
        })
        .catch((error) => {
          whatsappTemplatesError = error?.message || 'Unable to load templates';
          whatsappTemplatesCache = [];
          throw error;
        })
        .finally(() => {
          whatsappTemplatesRequest = null;
        });
      whatsappTemplatesRequest = request;
      return request;
    };

    const configureWhatsAppTemplateModal = (modal, node) => {
      if (!modal) return;
      const listEl = modal.querySelector('#wa-template-list');
      const emptyState = modal.querySelector('#wa-template-empty');
      const configWrap = modal.querySelector('#wa-template-config');
      const titleEl = modal.querySelector('#wa-template-title');
      const metaEl = modal.querySelector('#wa-template-meta');
      const previewEl = modal.querySelector('#wa-template-preview');
      const mappingContainer = modal.querySelector('#wa-template-mapping');
      const phoneModeSelect = modal.querySelector('#wa-template-phone-mode');
      const phoneValueInput = modal.querySelector('#wa-template-phone-value');
      const saveButton = modal.querySelector('#wa-template-save');
      const deleteButton = modal.querySelector('#wa-template-delete');

      if (listEl) {
        listEl.innerHTML = '<div class="list-group-item text-center py-4 text-muted"><div class="spinner-border spinner-border-sm text-primary me-2" role="status"></div>Loading templates…</div>';
      }

      const nodeConfig = manager.deepClone(node.config || {});
      const existingTemplate = (nodeConfig && typeof nodeConfig.template === 'object') ? normaliseTemplate(nodeConfig.template) : null;
      const existingMapping = (nodeConfig && typeof nodeConfig.mapping === 'object') ? manager.deepClone(nodeConfig.mapping) : {};
      let availableTemplates = [];
      let currentTemplate = null;
      let selectedTemplateKey = existingTemplate ? String(existingTemplate.id || existingTemplate.name || '') : '';

      const setActiveTemplateButton = (key) => {
        if (!listEl) return;
        listEl.querySelectorAll('[data-template-key]').forEach((button) => {
          button.classList.toggle('active', button.dataset.templateKey === key);
        });
      };

      const renderPreview = (template) => {
        if (!previewEl) return;
        const placeholders = ensureArray(template?.placeholders);
        const components = ensureArray(template?.components);
        const parts = [];
        if (placeholders.length) {
          const items = placeholders
            .map((entry) => `<li>${escapeHtml(entry?.label || entry?.key || '')}</li>`)
            .join('');
          parts.push(`<div class="mb-2"><strong>Placeholders</strong><ul class="mb-0 ps-3">${items}</ul></div>`);
        }
        const componentBlocks = components
          .filter((component) => component && typeof component.text === 'string' && component.text)
          .map((component) => {
            const label = component.type ? String(component.type).toUpperCase() : 'TEXT';
            const body = escapeHtml(component.text).replace(/\n/g, '<br>');
            return `<div class="mb-2"><span class="badge text-bg-light text-uppercase me-2">${escapeHtml(label)}</span><span>${body}</span></div>`;
          });
        if (componentBlocks.length) {
          parts.push(`<div><strong>Sample content</strong>${componentBlocks.join('')}</div>`);
        }
        previewEl.innerHTML = parts.join('') || '<div class="text-muted">No preview available for this template.</div>';
      };

      const renderPlaceholderMappings = (template) => {
        if (!mappingContainer) return;
        mappingContainer.innerHTML = '';
        const placeholders = ensureArray(template?.placeholders);
        if (!placeholders.length) {
          mappingContainer.innerHTML = '<div class="text-muted small">This template does not require placeholders.</div>';
          return;
        }
        const existingEntries = new Map();
        ensureArray(existingMapping?.placeholders).forEach((entry) => {
          if (entry && entry.key) {
            existingEntries.set(String(entry.key), entry);
          }
        });
        placeholders.forEach((placeholder, index) => {
          const key = String(placeholder?.key || `placeholder_${index}`);
          const entry = existingEntries.get(key) || {};
          const inferredMode = (entry.mode || (entry.path ? 'field' : (entry.value ? 'literal' : 'field')) || 'field').toLowerCase();
          const mode = inferredMode === 'literal' ? 'literal' : 'field';
          const resolvedValue = mode === 'literal'
            ? (entry.value ?? '')
            : (entry.path ?? entry.value ?? '');
          const badgeLabel = placeholder?.component ? String(placeholder.component).toUpperCase() : 'VALUE';
          const labelText = placeholder?.label || key;
          const row = document.createElement('div');
          row.className = 'mb-3';
          row.dataset.placeholderKey = key;
          row.dataset.placeholderLabel = labelText;
          row.dataset.placeholderComponent = placeholder?.component || '';
          row.dataset.placeholderType = placeholder?.type || '';
          row.innerHTML = `
            <div class="d-flex align-items-center gap-2 mb-1">
              <span class="badge text-bg-secondary text-uppercase">${escapeHtml(badgeLabel)}</span>
              <span class="small">${escapeHtml(labelText)}</span>
            </div>
            <div class="input-group input-group-sm">
              <select class="form-select" data-role="mode">
                <option value="field"${mode === 'field' ? ' selected' : ''}>Payload field</option>
                <option value="literal"${mode === 'literal' ? ' selected' : ''}>Fixed value</option>
              </select>
              <input type="text" class="form-control" data-role="value" placeholder="e.g. customer.name" value="${escapeHtml(resolvedValue || '')}">
            </div>
            <div class="form-text">Use dot notation to read from the payload or enter a fixed value.</div>
          `;
          mappingContainer.appendChild(row);
        });
      };

      const applyTemplate = (template) => {
        currentTemplate = template ? normaliseTemplate(template) : null;
        const hasTemplate = Boolean(currentTemplate);
        if (emptyState) emptyState.classList.toggle('d-none', hasTemplate);
        if (configWrap) configWrap.classList.toggle('d-none', !hasTemplate);
        if (!currentTemplate) {
          if (saveButton) saveButton.disabled = true;
          return;
        }
        selectedTemplateKey = String(currentTemplate.id || currentTemplate.name || '');
        setActiveTemplateButton(selectedTemplateKey);
        if (titleEl) {
          titleEl.textContent = currentTemplate.name || currentTemplate.id || 'WhatsApp Template';
        }
        if (metaEl) {
          const badges = [];
          if (currentTemplate.status) {
            badges.push(`<span class="badge text-bg-success">${escapeHtml(currentTemplate.status)}</span>`);
          }
          if (currentTemplate.language) {
            badges.push(`<span class="badge text-bg-light text-uppercase">${escapeHtml(currentTemplate.language)}</span>`);
          }
          if (currentTemplate.category) {
            badges.push(`<span class="badge text-bg-light">${escapeHtml(currentTemplate.category)}</span>`);
          }
          metaEl.innerHTML = badges.join(' ');
        }
        if (phoneModeSelect && phoneValueInput) {
          const phoneConfig = existingMapping?.phone || {};
          const inferredMode = (phoneConfig.mode || (phoneConfig.path ? 'field' : (phoneConfig.value ? 'literal' : 'field')) || 'field').toLowerCase();
          const mode = inferredMode === 'literal' ? 'literal' : 'field';
          const value = mode === 'literal'
            ? (phoneConfig.value ?? '')
            : (phoneConfig.path ?? phoneConfig.value ?? '');
          phoneModeSelect.value = mode;
          phoneValueInput.value = value || '';
        }
        renderPlaceholderMappings(currentTemplate);
        renderPreview(currentTemplate);
        if (saveButton) saveButton.disabled = false;
      };

      const renderTemplateButtons = (templates) => {
        if (!listEl) return;
        listEl.innerHTML = '';
        if (!templates.length) {
          const message = document.createElement('div');
          message.className = 'list-group-item text-muted small';
          message.textContent = whatsappTemplatesError || 'No templates available.';
          listEl.appendChild(message);
          return;
        }
        templates.forEach((template) => {
          const key = String(template.id || template.name || '');
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-start';
          button.dataset.templateKey = key;
          const language = template.language ? escapeHtml(template.language) : '';
          const category = template.category ? escapeHtml(template.category) : '';
          const status = template.status ? `<span class="badge text-bg-success">${escapeHtml(template.status)}</span>` : '';
          button.innerHTML = `
            <div class="me-2">
              <div class="fw-semibold">${escapeHtml(template.name || template.id || 'Template')}</div>
              <div class="small text-muted">${language}${language && category ? ' · ' : ''}${category}</div>
            </div>
            ${status}
          `;
          button.addEventListener('click', () => {
            applyTemplate(template);
          });
          listEl.appendChild(button);
        });
        if (selectedTemplateKey) {
          setActiveTemplateButton(selectedTemplateKey);
        }
      };

      const collectMapping = () => {
        const mapping = { placeholders: [] };
        if (phoneModeSelect && phoneValueInput) {
          const modeRaw = (phoneModeSelect.value || 'field').toLowerCase();
          const mode = modeRaw === 'literal' ? 'literal' : 'field';
          const rawValue = phoneValueInput.value.trim();
          mapping.phone = {
            mode,
            path: mode === 'literal' ? '' : rawValue,
            value: rawValue,
          };
        }
        if (mappingContainer) {
          mappingContainer.querySelectorAll('[data-placeholder-key]').forEach((row) => {
            const key = row.dataset.placeholderKey || '';
            if (!key) return;
            const label = row.dataset.placeholderLabel || '';
            const component = row.dataset.placeholderComponent || '';
            const type = row.dataset.placeholderType || '';
            const select = row.querySelector('select[data-role="mode"]');
            const input = row.querySelector('input[data-role="value"]');
            const modeRaw = (select?.value || 'field').toLowerCase();
            const mode = modeRaw === 'literal' ? 'literal' : 'field';
            const rawValue = input?.value?.trim() || '';
            const entry = {
              key,
              label,
              component,
              type,
              mode,
              path: mode === 'literal' ? '' : rawValue,
              value: rawValue,
            };
            mapping.placeholders.push(entry);
          });
        }
        return mapping;
      };

      const loadTemplates = async () => {
        try {
          availableTemplates = await fetchWhatsAppTemplates();
          if (existingTemplate) {
            const fallbackKey = String(existingTemplate.id || existingTemplate.name || '');
            if (fallbackKey && !availableTemplates.some((template) => String(template.id || template.name || '') === fallbackKey)) {
              availableTemplates = [existingTemplate, ...availableTemplates];
            }
          }
          renderTemplateButtons(availableTemplates);
          const initialKey = selectedTemplateKey;
          if (initialKey) {
            const match = availableTemplates.find((template) => String(template.id || template.name || '') === initialKey);
            if (match) {
              applyTemplate(match);
              return;
            }
          }
          if (!availableTemplates.length && existingTemplate) {
            applyTemplate(existingTemplate);
          }
        } catch (error) {
          if (listEl) {
            listEl.innerHTML = `<div class="list-group-item text-danger small">${escapeHtml(error?.message || 'Failed to load templates')}</div>`;
          }
          if (existingTemplate) {
            applyTemplate(existingTemplate);
          }
        }
      };

      if (deleteButton) {
        deleteButton.onclick = (event) => {
          event.preventDefault();
          if (attemptNodeRemoval(node.id)) {
            hideModal(modal);
          }
        };
      }

      if (saveButton) {
        saveButton.onclick = (event) => {
          event.preventDefault();
          if (!currentTemplate) {
            window.alert('Select a WhatsApp template before saving.');
            return;
          }
          if (phoneModeSelect && phoneValueInput) {
            const value = phoneValueInput.value.trim();
            if (!value) {
              window.alert('Specify where to obtain the recipient phone number.');
              return;
            }
          }
          const mapping = collectMapping();
          const nextConfig = manager.deepClone(nodeConfig || {});
          nextConfig.template = {
            id: currentTemplate.id,
            name: currentTemplate.name,
            language: currentTemplate.language,
            category: currentTemplate.category,
            status: currentTemplate.status,
            placeholders: manager.deepClone(currentTemplate.placeholders),
            requirements: manager.deepClone(currentTemplate.requirements),
            components: manager.deepClone(currentTemplate.components),
          };
          nextConfig.mapping = mapping;
          const originalName = node.name || '';
          const defaultName = 'WhatsApp Template';
          const computedName = currentTemplate.name ? `WhatsApp: ${currentTemplate.name}` : defaultName;
          manager.updateNode(node.id, (existing) => {
            const nextName = (!originalName || originalName === defaultName) ? computedName : originalName;
            existing.name = nextName;
            existing.config = nextConfig;
            computePorts(existing);
            return existing;
          });
          render();
          hideModal(modal);
        };
      }

      loadTemplates();
    };

    const configureRawModal = (modal, node) => {
      if (!modal) return;
      const form = modal.querySelector('#form-raw');
      if (!form) return;
      const nameInput = form.querySelector('input[name="name"]');
      const kindInput = form.querySelector('input[name="kind"]');
      const configArea = form.querySelector('textarea[name="config"]');
      if (nameInput) nameInput.value = node.name || node.kind || 'Node';
      if (kindInput) kindInput.value = node.kind || '';
      if (configArea) {
        try {
          configArea.value = JSON.stringify(node.config || {}, null, 2);
        } catch (error) {
          configArea.value = '{}';
        }
      }
      form.onsubmit = (event) => {
        event.preventDefault();
        const nameValue = nameInput ? nameInput.value.trim() : node.name;
        let parsed = node.config || {};
        if (configArea) {
          try {
            parsed = configArea.value ? JSON.parse(configArea.value) : {};
          } catch (error) {
            window.alert(`Invalid JSON: ${error.message}`);
            return;
          }
        }
        manager.updateNode(node.id, (existing) => {
          existing.name = nameValue || existing.kind;
          existing.config = parsed;
          computePorts(existing);
          return existing;
        });
        render();
        hideModal(modal);
      };
      const deleteBtn = modal.querySelector('#raw-delete');
      if (deleteBtn) {
        deleteBtn.onclick = (event) => {
          event.preventDefault();
          if (attemptNodeRemoval(node.id)) {
            hideModal(modal);
          }
        };
      }
    };

    const configureAgentModal = (modal, node) => {
      if (!modal) return;
      const form = modal.querySelector('#form-agent');
      if (!form) return;
      const config = manager.deepClone(node.config || {});
      const modelSettings = typeof config.model_settings === 'object' && config.model_settings ? config.model_settings : {};
      const tools = Array.isArray(config.tools) ? config.tools.slice() : [];
      const nameInput = form.querySelector('input[name="name"]');
      const instructionsInput = form.querySelector('textarea[name="instructions"]');
      const inputMessageInput = form.querySelector('textarea[name="input_message"]');
      const inputRoleSelect = form.querySelector('select[name="input_role"]');
      const includeHistory = form.querySelector('input[name="include_chat_history"]');
      const modelSelect = form.querySelector('select[name="model"]');
      const outputFormat = form.querySelector('select[name="output_format"]');
      const reasoningSelect = form.querySelector('select[name="reasoning_effort"]');
      const continueOnError = form.querySelector('input[name="continue_on_error"]');
      const writeHistory = form.querySelector('input[name="write_to_conversation_history"]');
      const toolChoice = form.querySelector('select[name="tool_choice"]');
      const temperature = form.querySelector('input[name="temperature"]');
      const maxTokens = form.querySelector('input[name="max_tokens"]');
      const topP = form.querySelector('input[name="top_p"]');
      const toolsContainer = modal.querySelector('#agent-tools');
      const addToolButton = modal.querySelector('#agent-add-tool');

      if (nameInput) nameInput.value = node.name || config.name || 'Agent';
      if (instructionsInput) instructionsInput.value = config.instructions || '';
      if (inputMessageInput) inputMessageInput.value = config.input_message || '';
      if (inputRoleSelect) inputRoleSelect.value = config.input_role || 'user';
      if (includeHistory) includeHistory.checked = config.include_chat_history !== false;
      if (modelSelect) modelSelect.value = config.model || 'gpt-4o-mini';
      if (outputFormat) outputFormat.value = config.output_format || 'text';
      if (reasoningSelect) reasoningSelect.value = config.reasoning_effort || '';
      if (continueOnError) continueOnError.checked = Boolean(config.continue_on_error);
      if (writeHistory) writeHistory.checked = config.write_to_conversation_history !== false;
      if (toolChoice) toolChoice.value = modelSettings.tool_choice || 'auto';
      if (temperature) temperature.value = modelSettings.temperature ?? '';
      if (maxTokens) maxTokens.value = modelSettings.max_tokens ?? '';
      if (topP) topP.value = modelSettings.top_p ?? '';

      const updateTools = () => {
        renderToolsChips(toolsContainer, tools, (index) => {
          tools.splice(index, 1);
          updateTools();
        });
      };
      updateTools();

      if (addToolButton) {
        addToolButton.onclick = (event) => {
          event.preventDefault();
          const value = window.prompt('Tool name (e.g. "web_search")');
          if (value) {
            tools.push(value.trim());
            updateTools();
          }
        };
      }

      form.onsubmit = (event) => {
        event.preventDefault();
        const nextName = nameInput ? nameInput.value.trim() : node.name;
        const tempValue = temperature && temperature.value !== '' ? Number(temperature.value) : undefined;
        const tokensValue = maxTokens && maxTokens.value !== '' ? Number(maxTokens.value) : undefined;
        const topPValue = topP && topP.value !== '' ? Number(topP.value) : undefined;

        const modelSettingsNext = {
          tool_choice: toolChoice ? toolChoice.value : modelSettings.tool_choice,
        };
        if (tempValue !== undefined && !Number.isNaN(tempValue)) {
          modelSettingsNext.temperature = tempValue;
        }
        if (tokensValue !== undefined && !Number.isNaN(tokensValue)) {
          modelSettingsNext.max_tokens = tokensValue;
        }
        if (topPValue !== undefined && !Number.isNaN(topPValue)) {
          modelSettingsNext.top_p = topPValue;
        }

        const nextConfig = {
          name: nextName || node.kind,
          instructions: instructionsInput ? instructionsInput.value : '',
          input_message: inputMessageInput ? inputMessageInput.value : '',
          input_role: inputRoleSelect ? inputRoleSelect.value : 'user',
          include_chat_history: includeHistory ? includeHistory.checked : true,
          model: modelSelect ? modelSelect.value : config.model,
          tools: tools.slice(),
          output_format: outputFormat ? outputFormat.value : config.output_format,
          reasoning_effort: reasoningSelect ? reasoningSelect.value : config.reasoning_effort,
          continue_on_error: continueOnError ? continueOnError.checked : Boolean(config.continue_on_error),
          write_to_conversation_history: writeHistory ? writeHistory.checked : config.write_to_conversation_history !== false,
          model_settings: modelSettingsNext,
        };
        manager.updateNode(node.id, (existing) => {
          existing.name = nextName || existing.kind;
          existing.config = nextConfig;
          computePorts(existing);
          return existing;
        });
        render();
        hideModal(modal);
      };

      const deleteBtn = modal.querySelector('#agent-delete');
      if (deleteBtn) {
        deleteBtn.onclick = (event) => {
          event.preventDefault();
        if (attemptNodeRemoval(node.id)) {
          hideModal(modal);
        }
        };
      }
    };

    const describeWebhook = (webhook) => {
      if (!webhook) return '';
      const parts = [
        `<div class="fw-semibold">${escapeHtml(webhook.name || '')}</div>`,
      ];
      if (webhook.description) {
        parts.push(`<div>${escapeHtml(webhook.description)}</div>`);
      }
      if (webhook.url) {
        const safeUrl = escapeHtml(webhook.url);
        parts.push(`<div class="mt-1 text-break"><a href="${safeUrl}" target="_blank" rel="noopener">${safeUrl}</a></div>`);
      }
      if (webhook.expected_content_type) {
        parts.push(`<div class="mt-1"><span class="badge text-bg-light">${escapeHtml(webhook.expected_content_type)}</span></div>`);
      }
      return parts.join('');
    };

    const getWebhookById = (value) => {
      if (!value && value !== 0) return null;
      return availableWebhooks.find((webhook) => String(webhook.id) === String(value)) || null;
    };

    const renderWebhookOptions = (preferredId) => {
      const { select } = webhookModalState;
      if (!select) return;
      const fallback = typeof preferredId !== 'undefined' ? String(preferredId) : select.value;
      select.innerHTML = '<option value="">-- Create new webhook --</option>';
      availableWebhooks.forEach((webhook) => {
        const option = document.createElement('option');
        option.value = String(webhook.id);
        option.textContent = webhook.name || webhook.id;
        select.appendChild(option);
      });
      if (fallback && availableWebhooks.some((webhook) => String(webhook.id) === String(fallback))) {
        select.value = String(fallback);
      } else {
        select.value = '';
      }
    };

    const syncWebhookModalDetails = () => {
      if (typeof webhookModalState.updateNameVisibility === 'function') {
        webhookModalState.updateNameVisibility();
      }
      if (typeof webhookModalState.updateDetails === 'function') {
        webhookModalState.updateDetails();
      }
    };

    const handleWebhookListUpdated = (preferredId) => {
      renderWebhookOptions(preferredId);
      syncWebhookModalDetails();
    };

    const openWebhookCreationModal = () => {
      const modalEl = document.getElementById('webhookBuilderModal');
      const modalContent = document.getElementById('webhook-builder-modal-content');
      if (!modalEl || typeof bootstrap === 'undefined') {
        warn('Webhook creation modal is unavailable.');
        return;
      }

      if (modalContent) {
        modalContent.innerHTML = '<div class="p-4 text-center"><div class="spinner-border" role="status"></div><p class="mt-3 mb-0">Loading webhook form…</p></div>';
      }

      const modalInstance = bootstrap.Modal.getOrCreateInstance(modalEl);
      modalInstance.show();

      if (!webhookCreateUrl || typeof fetch !== 'function') {
        if (modalContent) {
          modalContent.innerHTML = '<div class="p-4"><div class="alert alert-danger">Webhook creation is unavailable in this environment.</div><div class="text-end"><button class="btn btn-secondary" data-bs-dismiss="modal">Close</button></div></div>';
        }
        return;
      }

      let requestUrl = webhookCreateUrl;
      try {
        const url = new URL(webhookCreateUrl, window.location.origin);
        if (flowId) {
          url.searchParams.set('flow_id', flowId);
        }
        requestUrl = url.toString();
      } catch (error) {
        warn('Failed to build webhook creation URL', error);
      }

      fetch(requestUrl, {
        headers: {
          'HX-Request': 'true',
          'X-Requested-With': 'XMLHttpRequest',
        },
      })
        .then((response) => {
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }
          return response.text();
        })
        .then((html) => {
          if (modalContent) {
            modalContent.innerHTML = html;
          }
          try {
            document.body.dispatchEvent(new CustomEvent('htmx:afterSwap', { detail: { target: modalContent } }));
          } catch (error) {
            warn('Failed to dispatch htmx:afterSwap for webhook modal', error);
          }
        })
        .catch((error) => {
          if (modalContent) {
            modalContent.innerHTML = `<div class="p-4"><div class="alert alert-danger">Failed to load webhook form: ${escapeHtml(error.message)}</div><div class="text-end"><button class="btn btn-secondary" data-bs-dismiss="modal">Close</button></div></div>`;
          }
          warn('Failed to load webhook creation form', error);
        });
    };

    const refreshAvailableWebhooks = () => {
      if (!webhookListUrl || typeof fetch !== 'function') {
        return Promise.resolve(availableWebhooks);
      }

      return fetch(webhookListUrl, {
        headers: {
          Accept: 'application/json',
        },
      })
        .then((response) => {
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }
          return response.json();
        })
        .then((payload) => {
          const nextList = Array.isArray(payload?.webhooks)
            ? payload.webhooks.map(normaliseWebhookEntry)
            : [];
          availableWebhooks = nextList;
          handleWebhookListUpdated();
          return availableWebhooks;
        })
        .catch((error) => {
          warn('Failed to refresh available webhooks', error);
          return availableWebhooks;
        });
    };

    ['webhookConfigAdded', 'webhookConfigUpdated', 'webhookConfigDeleted'].forEach((eventName) => {
      addListener(document, eventName, () => {
        refreshAvailableWebhooks();
      });
    });

    const configureTriggerWebhookModal = (modal, node) => {
      if (!modal) return;
      const form = modal.querySelector('#form-trigger-webhook');
      if (!form) return;
      const nameInput = form.querySelector('input[name="name"]');
      const select = form.querySelector('select[name="webhook_id"]');
      const customNameInput = form.querySelector('input[name="webhook_name"]');
      const details = modal.querySelector('#trigger-webhook-details');
      const nameWrap = modal.querySelector('#webhook-name-input');
      const createButton = modal.querySelector('#btnCreateWebhookInPanel');
      const config = node.config || {};

      if (nameInput) nameInput.value = node.name || config.name || 'Webhook Trigger';
      if (customNameInput) customNameInput.value = config.webhook_name || '';

      const updateNameVisibility = () => {
        if (!select || !nameWrap) return;
        if (!select.value) {
          nameWrap.style.display = 'block';
        } else {
          nameWrap.style.display = 'none';
        }
      };

      const updateDetails = () => {
        if (!details) return;
        const selected = select && select.value ? getWebhookById(select.value) : null;
        if (!selected) {
          if (!select || select.value || availableWebhooks.length) {
            details.style.display = 'none';
            details.innerHTML = '';
          } else {
            details.style.display = 'block';
            details.innerHTML = '<div class="text-muted"><i class="bi bi-info-circle"></i> No existing webhooks. A new webhook will be created for this flow.</div>';
          }
          return;
        }
        details.style.display = 'block';
        details.innerHTML = describeWebhook(selected);
      };

      webhookModalState.select = select || null;
      webhookModalState.details = details || null;
      webhookModalState.nameWrap = nameWrap || null;
      webhookModalState.customNameInput = customNameInput || null;
      webhookModalState.updateNameVisibility = updateNameVisibility;
      webhookModalState.updateDetails = updateDetails;

      if (modal) {
        addListener(modal, 'hidden.bs.modal', () => {
          if (webhookModalState.select === select) {
            webhookModalState.select = null;
            webhookModalState.details = null;
            webhookModalState.nameWrap = null;
            webhookModalState.customNameInput = null;
            webhookModalState.updateNameVisibility = null;
            webhookModalState.updateDetails = null;
          }
        });
      }

      if (select) {
        handleWebhookListUpdated(config.webhook_id ? String(config.webhook_id) : undefined);
      } else {
        syncWebhookModalDetails();
      }

      updateNameVisibility();
      updateDetails();

      if (select) {
        select.onchange = () => {
          const selected = getWebhookById(select.value);
          if (selected && customNameInput && !customNameInput.value) {
            customNameInput.value = selected.name || '';
          }
          updateNameVisibility();
          updateDetails();
        };
      }

      if (createButton) {
        createButton.onclick = (event) => {
          event.preventDefault();
          if (select) {
            select.value = '';
          }
          updateNameVisibility();
          if (customNameInput) {
            customNameInput.value = '';
            customNameInput.focus();
          }
          updateDetails();
          openWebhookCreationModal();
        };
      }

      form.onsubmit = (event) => {
        event.preventDefault();
        const selected = select && select.value ? getWebhookById(select.value) : null;
        const nextConfig = { ...(node.config || {}) };
        nextConfig.webhook_id = select ? select.value : '';
        nextConfig.webhook_name = customNameInput ? customNameInput.value.trim() || (selected?.name || '') : selected?.name || '';
        if (selected) {
          nextConfig.webhook_description = selected.description || '';
          nextConfig.webhook_url = selected.url || '';
        }
        manager.updateNode(node.id, (existing) => {
          existing.name = nameInput ? (nameInput.value.trim() || 'Webhook Trigger') : (existing.name || 'Webhook Trigger');
          existing.config = nextConfig;
          computePorts(existing);
          return existing;
        });
        render();
        hideModal(modal);
      };

      const deleteBtn = modal.querySelector('#trigger-webhook-delete');
      if (deleteBtn) {
        deleteBtn.onclick = (event) => {
          event.preventDefault();
          if (attemptNodeRemoval(node.id)) {
            hideModal(modal);
          }
        };
      }
    };

    const configureBranchModal = (modal, node) => {
      if (!modal) return;
      const form = modal.querySelector('#form-branch');
      if (!form) return;
      node.config = node.config || { rules: [], else: false };
      if (!Array.isArray(node.config.rules) || !node.config.rules.length) {
        node.config.rules = [{ name: 'true' }, { name: 'false' }];
      }
      const nameInput = form.querySelector('input[name="name"]');
      const rulesContainer = modal.querySelector('#branch-rules');
      const addRuleButton = modal.querySelector('#branch-add');
      const elseToggle = modal.querySelector('#branch-else');
      if (nameInput) nameInput.value = node.name || 'Branch';
      if (elseToggle) elseToggle.checked = Boolean(node.config.else);

      const renderRules = () => {
        if (!rulesContainer) return;
        rulesContainer.innerHTML = '';
        (node.config.rules || []).forEach((rule, index) => {
          const row = document.createElement('div');
          row.className = 'd-flex gap-2';
          row.innerHTML = `
            <input class="form-control form-control-sm" placeholder="name (port label)" value="${escapeHtml(rule?.name || '')}" data-k="name" data-i="${index}">
            <input class="form-control form-control-sm" placeholder="expr (python)" value="${escapeHtml(rule?.expr || '')}" data-k="expr" data-i="${index}">
            <button class="btn btn-sm btn-outline-danger" type="button"><i class="bi bi-trash"></i></button>
          `;
          row.querySelectorAll('input').forEach((input) => {
            input.oninput = (event) => {
              const key = input.dataset.k;
              node.config.rules[index][key] = event.target.value;
              computePorts(node);
              render();
            };
          });
          const removeBtn = row.querySelector('button');
          if (removeBtn) {
            removeBtn.onclick = (event) => {
              event.preventDefault();
              node.config.rules.splice(index, 1);
              computePorts(node);
              renderRules();
              render();
            };
          }
          rulesContainer.appendChild(row);
        });
      };

      renderRules();

      if (addRuleButton) {
        addRuleButton.onclick = (event) => {
          event.preventDefault();
          node.config.rules = node.config.rules || [];
          node.config.rules.push({ name: `rule_${node.config.rules.length + 1}`, expr: 'True' });
          computePorts(node);
          renderRules();
          render();
        };
      }

      if (elseToggle) {
        elseToggle.onchange = (event) => {
          node.config.else = event.target.checked;
          computePorts(node);
          render();
        };
      }

      form.onsubmit = (event) => {
        event.preventDefault();
        const nextName = nameInput ? nameInput.value.trim() : node.name;
        manager.updateNode(node.id, (existing) => {
          existing.name = nextName || 'Branch';
          existing.config = { ...node.config };
          computePorts(existing);
          return existing;
        });
        render();
        hideModal(modal);
      };

      const deleteBtn = modal.querySelector('#branch-delete');
      if (deleteBtn) {
        deleteBtn.onclick = (event) => {
          event.preventDefault();
          if (attemptNodeRemoval(node.id)) {
            hideModal(modal);
          }
        };
      }
    };

    const configureWhileModal = (modal, node) => {
      if (!modal) return;
      const form = modal.querySelector('#form-while');
      if (!form) return;
      node.config = node.config || { expr: 'True' };
      const nameInput = form.querySelector('input[name="name"]');
      const exprInput = form.querySelector('[name="expr"]');
      if (nameInput) nameInput.value = node.name || 'While';
      if (exprInput) exprInput.value = node.config.expr || 'True';

      form.onsubmit = (event) => {
        event.preventDefault();
        manager.updateNode(node.id, (existing) => {
          existing.name = nameInput ? (nameInput.value.trim() || 'While') : (existing.name || 'While');
          existing.config = { expr: exprInput ? exprInput.value || 'True' : 'True' };
          computePorts(existing);
          return existing;
        });
        render();
        hideModal(modal);
      };

      const deleteBtn = modal.querySelector('#while-delete');
      if (deleteBtn) {
        deleteBtn.onclick = (event) => {
          event.preventDefault();
          if (attemptNodeRemoval(node.id)) {
            hideModal(modal);
          }
        };
      }
    };

    const openEditor = (node) => {
      if (!node) return;
      const modal = getModalForKind(node.kind);
      if (!modal) return;
      const handlerMap = {
        agent: configureAgentModal,
        trigger_webhook: configureTriggerWebhookModal,
        logic_branch: configureBranchModal,
        logic_while: configureWhileModal,
        tool_send_whatsapp_template: configureWhatsAppTemplateModal,
      };
      const handler = handlerMap[node.kind] || configureRawModal;
      handler(modal, node);
      if (typeof bootstrap !== 'undefined') {
        const instance = bootstrap.Modal.getOrCreateInstance(modal);
        instance.show();
      }
    };

    const getCsrfToken = () => {
      const element = document.querySelector('input[name="csrfmiddlewaretoken"]');
      if (element) return element.value;
      const cookie = document.cookie.split(';').map((c) => c.trim()).find((c) => c.startsWith('csrftoken='));
      return cookie ? decodeURIComponent(cookie.split('=')[1]) : '';
    };

    const postJson = async (url, body) => {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify(body || {}),
      });
      const triggerHeader = response.headers.get('HX-Trigger');
      if (triggerHeader) {
        try {
          const payload = JSON.parse(triggerHeader);
          Object.entries(payload).forEach(([eventName, detail]) => {
            document.body.dispatchEvent(new CustomEvent(eventName, { detail }));
          });
        } catch (error) {
          warn('Unable to parse HX-Trigger header', error);
        }
      }
      const text = await response.text();
      if (text) {
        applyOobHtml(text);
      }
      if (!response.ok && response.status !== 204) {
        throw new Error(text || `Request failed (${response.status})`);
      }
      return { response, text };
    };

    const toolbar = document.querySelector('.page-header .btn-group');
    const getGraphPayload = () => manager.cloneGraph();

    if (toolbar) {
      const saveButton = toolbar.querySelector('button[data-action="save"]');
      const previewButton = toolbar.querySelector('button[data-action="preview"]');
      const runButton = toolbar.querySelector('button[data-action="run"]');
      const publishButton = toolbar.querySelector('button[data-action="publish"]');

      if (saveButton) {
        addListener(saveButton, 'click', async () => {
          const url = saveButton.dataset.url;
          if (!url) return;
          try {
            await postJson(url, { graph: getGraphPayload() });
          } catch (error) {
            console.error('[FlowBuilder][render]', 'Save failed', error);
          }
        });
      }

      if (publishButton) {
        addListener(publishButton, 'click', async () => {
          const url = publishButton.dataset.url;
          if (!url) return;
          try {
            await postJson(url, { graph: getGraphPayload() });
          } catch (error) {
            console.error('[FlowBuilder][render]', 'Publish failed', error);
          }
        });
      }

      if (previewButton) {
        addListener(previewButton, 'click', async () => {
          const url = previewButton.dataset.url;
          if (!url) return;
          const runId = (global.crypto?.randomUUID && global.crypto.randomUUID()) || String(Date.now());
          const graph = getGraphPayload();
          const payload = graph.nodes.find((node) => node.kind === 'trigger_manual')?.config || {};
          global.__previewRunId = runId;
          try {
            await postJson(url, { payload, run_id: runId, graph });
          } catch (error) {
            console.error('[FlowBuilder][render]', 'Preview failed', error);
          }
        });
      }

      if (runButton) {
        addListener(runButton, 'click', async () => {
          const url = runButton.dataset.url;
          if (!url) return;
          const graph = getGraphPayload();
          const payload = graph.nodes.find((node) => node.kind === 'trigger_manual')?.config || {};
          try {
            await postJson(url, { payload });
          } catch (error) {
            console.error('[FlowBuilder][render]', 'Manual run failed', error);
          }
        });
      }
    }

    const updateVersionBadge = (detail) => {
      const badge = document.getElementById('builderVersionBadge');
      if (!badge || !detail) return;
      badge.textContent = detail.version || badge.dataset.versionLabel || badge.textContent;
      badge.dataset.versionId = detail.version_id || '';
      badge.dataset.versionLabel = detail.version || '';
      badge.dataset.versionPublished = detail.is_published ? 'true' : 'false';
      badge.classList.remove('bg-success', 'bg-warning', 'text-dark');
      if (detail.is_published) {
        badge.classList.add('bg-success');
      } else {
        badge.classList.add('bg-warning', 'text-dark');
      }
    };

    const updateFlowStatus = (status) => {
      const tag = document.getElementById('flowStatusTag');
      if (!tag || typeof status !== 'string') return;
      tag.textContent = status.charAt(0).toUpperCase() + status.slice(1);
      tag.dataset.flowStatus = status;
    };

    const previewLog = document.getElementById('preview-log');
    const previewStreamEl = document.getElementById('preview-stream');
    const previewClearButton = document.getElementById('btn-preview-clear');
    let previewSource = null;

    const appendPreviewHtml = (html) => {
      applyOobHtml(html);
    };

    const disconnectPreviewSource = () => {
      if (previewSource) {
        previewSource.close();
        previewSource = null;
      }
    };

    const connectPreviewStream = (url) => {
      if (!url || !previewLog) return;
      disconnectPreviewSource();
      previewSource = new EventSource(url);
      previewSource.onmessage = (event) => {
        appendPreviewHtml(event.data || '');
      };
      previewSource.onerror = () => {
        disconnectPreviewSource();
      };
    };

    if (previewClearButton && previewLog) {
      addListener(previewClearButton, 'click', () => {
        previewLog.innerHTML = '<div class="text-muted">Preview log will appear here…</div>';
      });
    }

    addListener(document.body, 'flow-saved', (event) => {
      updateVersionBadge(event.detail || {});
    });

    addListener(document.body, 'flow-published', (event) => {
      const detail = event.detail || {};
      updateVersionBadge(detail);
      if (detail.flow_status) {
        updateFlowStatus(detail.flow_status);
      }
    });

    addListener(document.body, 'preview-started', (event) => {
      const detail = event.detail || {};
      if (previewLog) {
        previewLog.innerHTML = '';
      }
      if (detail.run_id) {
        global.__previewRunId = detail.run_id;
      }
      if (previewStreamEl) {
        const base = previewStreamEl.dataset.baseStream || '';
        const streamUrl = detail.stream_url || (detail.run_id && base ? `${base}?run_id=${encodeURIComponent(detail.run_id)}` : null);
        if (streamUrl) {
          previewStreamEl.classList.remove('d-none');
          connectPreviewStream(streamUrl);
        }
      }
    });

    addListener(document.body, 'preview-finished', () => {
      disconnectPreviewSource();
    });

    addListener(document.body, 'flow-manual-run', (event) => {
      if (!previewLog) return;
      const detail = event.detail || {};
      if (!previewLog.dataset.manualInitialized) {
        previewLog.innerHTML = '';
        previewLog.dataset.manualInitialized = 'true';
      }
      const timestamp = new Date().toLocaleTimeString();
      if (detail.triggered) {
        const executionLabel = detail.execution_id
          ? `Execution ${escapeHtml(detail.execution_id)}`
          : 'Manual run triggered';
        const triggerKey = detail.trigger_key ? ` (${escapeHtml(detail.trigger_key)})` : '';
        previewLog.insertAdjacentHTML(
          'afterbegin',
          `<div class="preview-entry border-bottom pb-2 mb-2">
             <div><strong>${executionLabel}</strong>${triggerKey}</div>
             <div class="text-muted small">${escapeHtml(timestamp)}</div>
           </div>`
        );
      } else {
        const reason = detail.reason ? ` (${escapeHtml(detail.reason)})` : '';
        previewLog.insertAdjacentHTML(
          'afterbegin',
          `<div class="preview-entry border-bottom pb-2 mb-2 text-warning">
             <div><strong>Manual run skipped${reason}</strong></div>
             <div class="text-muted small">${escapeHtml(timestamp)}</div>
           </div>`
        );
      }
    });

    global.builderRender = render;
    global.builderSavePayload = () => ({ graph: manager.cloneGraph() });
    global.builderPublishPayload = () => ({ graph: manager.cloneGraph() });
    global.builderPreviewPayload = () => {
      const runId = (global.crypto?.randomUUID && global.crypto.randomUUID()) || String(Date.now());
      const graph = manager.cloneGraph();
      const payload = graph.nodes.find((node) => node.kind === 'trigger_manual')?.config || {};
      global.__previewRunId = runId;
      return { payload, run_id: runId, graph };
    };

    global.openEditor = openEditor;

    const initializeToolbar = () => {
      const saveButton = document.querySelector('button[data-action="save"]');
      if (saveButton) {
        addListener(saveButton, 'click', () => {
          saveButton.blur();
        });
      }
    };

    initializeToolbar();

    render();
    resetPanToCenter();
    applyTransform();

    log('Flow builder initialised', { flowId });

    return {
      destroy() {
        disconnectPreviewSource();
        while (cleanupCallbacks.length) {
          const fn = cleanupCallbacks.pop();
          try {
            fn();
          } catch (error) {
            warn('Cleanup callback failed', error);
          }
        }
        if (canvas) {
          canvas.innerHTML = '';
        }
        if (edgesLayer) {
          edgesLayer.innerHTML = '';
        }
        if (canvasWrap) {
          canvasWrap.classList.remove('panning');
        }
        Object.values(modalRegistry).forEach((modal) => hideModal(modal));
        if (edgeModalEl && typeof bootstrap !== 'undefined') {
          const instance = bootstrap.Modal.getInstance(edgeModalEl);
          if (instance) instance.hide();
        }
        disconnectPreviewSource();
        delete global.builderRender;
        delete global.builderSavePayload;
        delete global.builderPublishPayload;
        delete global.builderPreviewPayload;
        delete global.openEditor;
        delete global.__FLOW_BUILDER_ACTIVE__;
        manager.destroy();
      },
    };
  }

  global.FlowBuilder = FlowBuilder;

  const registerLifecycleModule = () => {
    const registry = (global.Modules = global.Modules || {});

    registry.FlowBuilder = {
      sanitize(root) {
        if (!root) return;
        const debugFlag = root.getAttribute('data-debug');
        const stageAttr = root.getAttribute('data-stage');
        const builderRoot = root.querySelector('#flowBuilderRoot');
        if (builderRoot && debugFlag != null) {
          builderRoot.dataset.debug = debugFlag;
        }
        if (builderRoot && stageAttr != null) {
          builderRoot.dataset.stage = stageAttr;
        }
      },
      init(root) {
        if (!root || !root.isConnected) {
          return;
        }
        const builderRoot = root.querySelector('#flowBuilderRoot');
        if (!builderRoot) {
          console.warn('[FlowBuilder]', 'Missing #flowBuilderRoot for module initialization.');
          return;
        }
        const flowId = root.getAttribute('data-flow-id');
        const debugFlag = root.getAttribute('data-debug');
        const stageAttr = root.getAttribute('data-stage');
        if (debugFlag != null) {
          builderRoot.dataset.debug = debugFlag;
        }
        if (stageAttr != null) {
          builderRoot.dataset.stage = stageAttr;
        }
        FlowBuilder.init(builderRoot, flowId);
      },
      destroy() {
        FlowBuilder.destroy();
      },
    };

    if (typeof document !== 'undefined' && typeof document.dispatchEvent === 'function') {
      try {
        document.dispatchEvent(new CustomEvent('module:registered', { detail: { name: 'FlowBuilder' } }));
      } catch (error) {
        // Ignore registration event errors to keep lifecycle resilient.
      }
    }
  };

  if (typeof document !== 'undefined' && (document.readyState === 'complete' || document.readyState === 'interactive')) {
    registerLifecycleModule();
  } else if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', registerLifecycleModule, { once: true });
  } else {
    global.addEventListener?.('load', registerLifecycleModule);
  }
})(window);
