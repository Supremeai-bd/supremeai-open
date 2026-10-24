import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusPill } from './StatusPill';

describe('StatusPill', () => {
  it('renders status text when no label given', () => {
    render(<StatusPill status="healthy" />);
    expect(screen.getByText('healthy')).toBeInTheDocument();
  });

  it('renders custom label', () => {
    render(<StatusPill status="healthy" label="All Good" />);
    expect(screen.getByText('All Good')).toBeInTheDocument();
    expect(screen.queryByText('healthy')).not.toBeInTheDocument();
  });

  it('falls back to unknown style for unrecognized status', () => {
    const { container } = render(<StatusPill status="weird" />);
    expect(container.querySelector('.bg-\\[\\#64748b\\]')).toBeTruthy();
  });

  it('applies sm size classes', () => {
    const { container } = render(<StatusPill status="active" size="sm" />);
    expect(container.querySelector('.text-\\[9px\\]')).toBeTruthy();
  });

  it('applies lg size classes', () => {
    const { container } = render(<StatusPill status="active" size="lg" />);
    expect(container.querySelector('.text-xs')).toBeTruthy();
  });

  it('omits ping animation when pulse is false', () => {
    const { container } = render(<StatusPill status="active" pulse={false} />);
    expect(container.querySelector('.hidden')).toBeTruthy();
  });
});
