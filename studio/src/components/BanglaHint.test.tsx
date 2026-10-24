import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BanglaHint } from './BanglaHint';

describe('BanglaHint', () => {
  it('renders a help button with bengali aria-label', () => {
    render(<BanglaHint text="টিপস টেক্সট" />);
    expect(screen.getByLabelText('টিপস')).toBeInTheDocument();
  });

  it('hides tooltip by default', () => {
    render(<BanglaHint text="টিপস টেক্সট" />);
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });

  it('shows tooltip on mouse enter and hides on leave', () => {
    render(<BanglaHint text="টিপস টেক্সট" />);
    const wrapper = screen.getByLabelText('টিপস').parentElement as HTMLElement;
    fireEvent.mouseEnter(wrapper);
    expect(screen.getByRole('tooltip')).toHaveTextContent('টিপস টেক্সট');
    fireEvent.mouseLeave(wrapper);
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });
});
