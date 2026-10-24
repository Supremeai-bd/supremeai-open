import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { GaugeRing } from './GaugeRing';

describe('GaugeRing', () => {
  it('renders the rounded percentage of the value', () => {
    const { container } = render(<GaugeRing value={42.6} />);
    expect(container.textContent).toContain('43%');
    expect(container.querySelector('svg')).toBeTruthy();
  });

  it('clamps values above 100', () => {
    const { container } = render(<GaugeRing value={150} />);
    expect(container.textContent).toContain('100%');
  });

  it('clamps values below 0', () => {
    const { container } = render(<GaugeRing value={-10} />);
    expect(container.textContent).toContain('0%');
  });

  it('renders label and sublabel', () => {
    const { container } = render(<GaugeRing value={50} label="CPU" sublabel="core" />);
    expect(container.textContent).toContain('CPU');
    expect(container.textContent).toContain('core');
  });

  it('applies tone class and custom size', () => {
    const { container } = render(<GaugeRing value={50} tone="amber" size={120} strokeWidth={8} />);
    expect(container.querySelector('.text-\\[\\#f59e0b\\]')).toBeTruthy();
    expect(container.querySelector('svg')?.getAttribute('width')).toBe('120');
  });

  it('defaults to cyan tone', () => {
    const { container } = render(<GaugeRing value={50} />);
    expect(container.querySelector('.text-\\[\\#00f3ff\\]')).toBeTruthy();
  });
});
