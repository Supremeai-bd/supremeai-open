import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { JsonViewer } from './JsonViewer';

describe('JsonViewer', () => {
  it('renders primitive values', () => {
    const { container } = render(<JsonViewer data={{ name: 'neo', age: 42, active: true, nil: null }} />);
    expect(container.textContent).toContain('neo');
    expect(container.textContent).toContain('42');
    expect(container.textContent).toContain('true');
    expect(container.textContent).toContain('null');
  });

  it('renders empty object', () => {
    const { container } = render(<JsonViewer data={{}} />);
    expect(container.textContent).toContain('{}');
  });

  it('renders empty array', () => {
    const { container } = render(<JsonViewer data={[]} />);
    expect(container.textContent).toContain('[]');
  });

  it('renders array values (auto-expanded at top level)', () => {
    render(<JsonViewer data={[1, 2, 3]} />);
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('collapses nested object node on click', () => {
    render(<JsonViewer data={{ a: { b: 1 } }} />);
    // top-level {1} and nested {1} both render because level < 2 auto-expands
    expect(screen.getAllByText('{1}').length).toBe(2);
    expect(screen.getByText('b')).toBeInTheDocument();
    const nestedToggle = screen.getAllByText('{1}')[1];
    fireEvent.click(nestedToggle);
    expect(screen.queryByText('b')).not.toBeInTheDocument();
  });

  it('respects defaultExpanded prop', () => {
    render(<JsonViewer data={{ a: 1 }} defaultExpanded />);
    expect(screen.getByText('a')).toBeInTheDocument();
  });
});
