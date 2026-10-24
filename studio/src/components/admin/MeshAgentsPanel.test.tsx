/**
 * MeshAgentsPanel tests — MESH-2 (issue #940).
 * Contract: connected-nodes list renders [node_id | icon | role dropdown |
 * last_seen | load]; changing the dropdown PATCHes /api/v1/nodes/{id};
 * PATCH failure rolls the dropdown back and shows an inline error.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MeshAgentsPanel } from './MeshAgentsPanel';

const NODE_A = {
  node_id: 'agent-alpha-01',
  node_type: 'coder',
  role: 'coder',
  load: { cpu_percent: 42 },
  last_seen: '2026-09-24T10:00:00Z',
  last_seen_epoch: Date.now() / 1000 - 30, // 30s ago → online
};

const NODE_B = {
  node_id: 'agent-beta-02',
  node_type: 'tester',
  role: 'observer',
  load: null,
  last_seen: '2026-09-24T09:00:00Z',
  last_seen_epoch: Date.now() / 1000 - 3600 * 2, // 2h ago → stale
};

function mockFetchOnce(respond: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
    Promise.resolve(respond(String(input), init)),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('MeshAgentsPanel (MESH-2)', () => {
  it('renders connected nodes with presence, load and role dropdowns', async () => {
    mockFetchOnce(() =>
      new Response(JSON.stringify({ nodes: [NODE_A, NODE_B] }), { status: 200 }),
    );

    render(<MeshAgentsPanel />);

    await waitFor(() => expect(screen.getByText('agent-alpha-01')).toBeTruthy());
    expect(screen.getByText('agent-beta-02')).toBeTruthy();
    // Presence badges: alpha online (30s), beta stale (2h)
    expect(screen.getByLabelText('online')).toBeTruthy();
    expect(screen.getByLabelText('stale')).toBeTruthy();
    // Load display for alpha
    expect(screen.getByText(/load 42%/)).toBeTruthy();
    // Role dropdowns exist per node with current role selected
    const alphaSelect = screen.getByLabelText('Role for agent-alpha-01') as HTMLSelectElement;
    expect(alphaSelect.value).toBe('coder');
  });

  it('PATCHes the node role when the dropdown changes (optimistic)', async () => {
    const fetchMock = mockFetchOnce(url => {
      if (url.endsWith('/api/v1/nodes')) {
        return new Response(JSON.stringify({ nodes: [NODE_A] }), { status: 200 });
      }
      throw new Error(`unexpected fetch ${url}`);
    });

    render(<MeshAgentsPanel />);
    const select = await screen.findByLabelText('Role for agent-alpha-01');

    // The PATCH URL is only used after a change → extend the mock now.
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/api/v1/nodes')) {
        return Promise.resolve(new Response(JSON.stringify({ nodes: [NODE_A] }), { status: 200 }));
      }
      if (url.includes('/api/v1/nodes/agent-alpha-01')) {
        expect(init?.method).toBe('PATCH');
        expect(JSON.parse(String(init?.body)).role).toBe('planner');
        return Promise.resolve(
          new Response(JSON.stringify({ node: { ...NODE_A, role: 'planner' } }), { status: 200 }),
        );
      }
      throw new Error(`unexpected fetch ${url}`);
    });

    fireEvent.change(select, { target: { value: 'planner' } });

    await waitFor(() =>
      expect((screen.getByLabelText('Role for agent-alpha-01') as HTMLSelectElement).value).toBe(
        'planner',
      ),
    );
  });

  it('rolls the role back and shows an inline error when PATCH fails', async () => {
    const fetchMock = mockFetchOnce(url => {
      if (url.endsWith('/api/v1/nodes')) {
        return new Response(JSON.stringify({ nodes: [NODE_A] }), { status: 200 });
      }
      throw new Error(`unexpected fetch ${url}`);
    });

    render(<MeshAgentsPanel />);
    const select = await screen.findByLabelText('Role for agent-alpha-01');

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/api/v1/nodes')) {
        return Promise.resolve(new Response(JSON.stringify({ nodes: [NODE_A] }), { status: 200 }));
      }
      if (url.includes('/api/v1/nodes/agent-alpha-01')) {
        return Promise.resolve(
          new Response(JSON.stringify({ detail: 'role not permitted' }), { status: 422 }),
        );
      }
      throw new Error(`unexpected fetch ${url}`);
    });

    fireEvent.change(select, { target: { value: 'gate' } });

    await waitFor(() =>
      expect((screen.getByLabelText('Role for agent-alpha-01') as HTMLSelectElement).value).toBe(
        'coder',
      ),
    );
    expect(screen.getByText(/role not permitted/)).toBeTruthy();
  });

  it('shows the empty state when no agents have checked in', async () => {
    mockFetchOnce(() => new Response(JSON.stringify({ nodes: [] }), { status: 200 }));
    render(<MeshAgentsPanel />);
    expect(await screen.findByText(/No mesh agents have checked in/)).toBeTruthy();
  });
});
