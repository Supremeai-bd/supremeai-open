import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { Skeleton, WorkspaceSkeleton } from './Skeleton';

describe('common/Skeleton', () => {
  it('renders rectangular variant by default', () => {
    const { container } = render(<Skeleton />);
    expect(container.firstElementChild?.className).toContain('rounded-xl');
  });

  it('renders circular variant', () => {
    const { container } = render(<Skeleton variant="circular" />);
    expect(container.firstElementChild?.className).toContain('rounded-full');
  });

  it('renders text variant', () => {
    const { container } = render(<Skeleton variant="text" />);
    expect(container.firstElementChild?.className).toContain('rounded');
    expect(container.firstElementChild?.className).toContain('h-4');
  });

  it('applies width and height styles', () => {
    const { container } = render(<Skeleton width={100} height={50} />);
    const el = container.firstElementChild as HTMLElement;
    expect(el.style.width).toBe('100px');
    expect(el.style.height).toBe('50px');
  });

  it('merges custom className', () => {
    const { container } = render(<Skeleton className="extra" />);
    expect(container.firstElementChild?.className).toContain('extra');
  });

  it('renders WorkspaceSkeleton layout', () => {
    const { container } = render(<WorkspaceSkeleton />);
    expect(container.firstElementChild?.className).toContain('bg-slate-950');
  });
});
