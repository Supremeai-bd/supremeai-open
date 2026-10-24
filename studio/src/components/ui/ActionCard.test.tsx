import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ActionCard } from './ActionCard';

describe('ActionCard', () => {
  it('renders title and description', () => {
    render(<ActionCard icon={<span>★</span>} title="Deploy" description="Ship it" />);
    expect(screen.getByText('Deploy')).toBeInTheDocument();
    expect(screen.getByText('Ship it')).toBeInTheDocument();
  });

  it('omits description when not provided', () => {
    render(<ActionCard icon={<span>★</span>} title="Deploy" />);
    expect(screen.getByText('Deploy')).toBeInTheDocument();
    expect(screen.queryByText('Ship it')).not.toBeInTheDocument();
  });

  it('calls onClick when clicked', () => {
    const onClick = vi.fn();
    render(<ActionCard icon={<span>★</span>} title="Deploy" onClick={onClick} />);
    screen.getByText('Deploy').click();
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('does not throw when onClick is omitted', () => {
    render(<ActionCard icon={<span>★</span>} title="Deploy" />);
    expect(() => screen.getByText('Deploy').click()).not.toThrow();
  });

  it('renders progress bar for loading variant', () => {
    const { container } = render(<ActionCard icon={<span>★</span>} title="Deploy" variant="loading" />);
    expect(container.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('applies success variant border class', () => {
    const { container } = render(<ActionCard icon={<span>★</span>} title="Deploy" variant="success" />);
    expect(container.querySelector('.border-\\[\\#10b981\\]')).toBeTruthy();
  });
});
