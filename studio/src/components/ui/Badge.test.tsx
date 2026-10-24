import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Badge } from './Badge';

describe('Badge', () => {
  it('renders children', () => {
    render(<Badge>NEW</Badge>);
    expect(screen.getByText('NEW')).toBeInTheDocument();
  });

  it('applies default variant classes', () => {
    render(<Badge>DEFAULT</Badge>);
    expect(screen.getByText('DEFAULT').className).toContain('bg-slate-950');
  });

  it('applies success variant classes', () => {
    render(<Badge variant="success">OK</Badge>);
    expect(screen.getByText('OK').className).toContain('bg-emerald-950');
  });

  it('applies danger variant classes', () => {
    render(<Badge variant="danger">ERR</Badge>);
    expect(screen.getByText('ERR').className).toContain('bg-red-950');
  });

  it('applies warning variant classes', () => {
    render(<Badge variant="warning">WARN</Badge>);
    expect(screen.getByText('WARN').className).toContain('bg-yellow-950');
  });

  it('applies info variant classes', () => {
    render(<Badge variant="info">INFO</Badge>);
    expect(screen.getByText('INFO').className).toContain('bg-cyan-950');
  });

  it('applies purple variant classes', () => {
    render(<Badge variant="purple">PRO</Badge>);
    expect(screen.getByText('PRO').className).toContain('bg-purple-950');
  });

  it('merges custom className', () => {
    render(<Badge className="custom-class">X</Badge>);
    expect(screen.getByText('X').className).toContain('custom-class');
  });
});
