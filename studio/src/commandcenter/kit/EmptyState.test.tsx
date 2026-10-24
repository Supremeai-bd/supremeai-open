import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EmptyState } from './EmptyState';

describe('EmptyState', () => {
  it('renders default bengali title and message', () => {
    render(<EmptyState />);
    expect(screen.getByText('ডেটা লোড হচ্ছে না')).toBeInTheDocument();
  });

  it('renders custom title and message', () => {
    render(<EmptyState title="Nothing here" message="Try later" />);
    expect(screen.getByText('Nothing here')).toBeInTheDocument();
    expect(screen.getByText('Try later')).toBeInTheDocument();
  });

  it('renders spinner when loading and no retry button', () => {
    const { container } = render(<EmptyState loading onRetry={vi.fn()} />);
    expect(container.querySelector('.animate-spin')).toBeTruthy();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('renders retry button and calls onRetry', () => {
    const onRetry = vi.fn();
    render(<EmptyState onRetry={onRetry} />);
    const btn = screen.getByRole('button');
    expect(btn).toBeInTheDocument();
    fireEvent.click(btn);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
