import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { SkeletonLoader } from './SkeletonLoader';

describe('SkeletonLoader', () => {
  it('renders default text type with shimmer', () => {
    const { container } = render(<SkeletonLoader />);
    const el = container.firstElementChild as HTMLElement;
    expect(el.className).toContain('animate-pulse');
    expect(container.querySelector('.animate-\\[shimmer_1\\.5s_infinite\\]')).toBeTruthy();
  });

  it('renders card type with rounded-2xl', () => {
    const { container } = render(<SkeletonLoader type="card" />);
    expect(container.firstElementChild?.className).toContain('rounded-2xl');
  });

  it('renders avatar type with rounded-full', () => {
    const { container } = render(<SkeletonLoader type="avatar" />);
    expect(container.firstElementChild?.className).toContain('rounded-full');
  });

  it('merges custom className', () => {
    const { container } = render(<SkeletonLoader className="my-4" />);
    expect(container.firstElementChild?.className).toContain('my-4');
  });
});
