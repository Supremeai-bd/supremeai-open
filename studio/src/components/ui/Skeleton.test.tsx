import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { Skeleton } from './Skeleton';

describe('Skeleton', () => {
  it('renders a div with pulse animation', () => {
    const { container } = render(<Skeleton />);
    const el = container.firstElementChild as HTMLElement;
    expect(el.tagName).toBe('DIV');
    expect(el.className).toContain('animate-pulse');
  });

  it('merges custom className', () => {
    const { container } = render(<Skeleton className="h-10 w-10" />);
    expect(container.firstElementChild?.className).toContain('h-10');
  });
});
