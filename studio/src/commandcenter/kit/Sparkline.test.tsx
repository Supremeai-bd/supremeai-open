import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Sparkline } from './Sparkline';

describe('Sparkline', () => {
  it('renders NO DATA for empty input', () => {
    render(<Sparkline data={[]} />);
    expect(screen.getByText('NO DATA')).toBeInTheDocument();
  });

  it('renders an svg with polyline for data', () => {
    const { container } = render(<Sparkline data={[1, 2, 3, 4, 5]} />);
    expect(container.querySelector('svg')).toBeTruthy();
    expect(container.querySelector('polyline')).toBeTruthy();
    expect(container.querySelector('polygon')).toBeTruthy();
  });

  it('respects custom dimensions', () => {
    const { container } = render(<Sparkline data={[1, 2, 3]} width={200} height={60} />);
    const svg = container.querySelector('svg');
    expect(svg?.getAttribute('width')).toBe('200');
    expect(svg?.getAttribute('height')).toBe('60');
  });

  it('handles constant data without divide-by-zero', () => {
    const { container } = render(<Sparkline data={[5, 5, 5, 5]} />);
    expect(container.querySelector('polyline')).toBeTruthy();
  });
});
