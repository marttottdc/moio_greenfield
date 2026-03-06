import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { DynamicNodeConfigForm } from '@/components/flow/NodeConfigForms';
import type { Node } from 'reactflow';
import { mergeNodeDataWithDefinitions, normalizeNodesForSave } from './flow-builder';

const noop = () => {};

describe('flow builder serialization', () => {
  it('preserves custom node forms after a save/load round trip', () => {
    const emailNode: Node<any> = {
      id: 'node_1',
      type: 'custom',
      position: { x: 0, y: 0 },
      data: {
        label: 'Send Email',
        type: 'action_email',
        description: 'Send a notification email',
        config: { to: 'person@example.com', subject: 'Hello' },
        formComponent: 'form_email',
        outputs: ['success'],
        inputs: ['input'],
        portSchemas: undefined,
      },
    };

    const [serializedNode] = normalizeNodesForSave([emailNode]);
    // normalizeNodesForSave returns backend node shape: { id, kind, name, x, y, config }
    // Flow load path builds SerializableNodeData before merging with definitions.
    const hydratedData = mergeNodeDataWithDefinitions({
      label: serializedNode.name,
      type: serializedNode.kind,
      config: serializedNode.config || {},
    }, {
      action_email: {
        kind: 'action_email',
        title: 'Send Email',
        icon: 'mail',
        category: 'Outputs',
        description: 'Send email',
        form_component: 'form_email',
        default_config: { subject: 'Hello' },
        ports: {
          in: [{ name: 'input' }],
          out: [{ name: 'success' }],
        },
      },
    });

    render(
      <DynamicNodeConfigForm
        formComponent={hydratedData.formComponent}
        nodeType={hydratedData.type}
        config={hydratedData.config || {}}
        onConfigChange={noop}
      />
    );

    expect(screen.getByTestId('input-email-to')).toBeInTheDocument();
  });
});
