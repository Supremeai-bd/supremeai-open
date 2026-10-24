import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { Input } from './Input';
import React from 'react';
import userEvent from '@testing-library/user-event';

describe('Input', () => {
  it('renders input correctly', () => {
    render(<Input placeholder="Enter text" />);
    expect(screen.getByPlaceholderText('Enter text')).toBeDefined();
  });

  it('renders label correctly', () => {
    render(<Input label="Username" id="username" />);
    expect(screen.getByText('Username')).toBeDefined();
  });

  it('renders helper text', () => {
    render(<Input helperText="Required field" />);
    expect(screen.getByText('Required field')).toBeDefined();
  });

  it('renders error message', () => {
    render(<Input error="Invalid input" helperText="Required field" />);
    expect(screen.getByText('Invalid input')).toBeDefined();
    expect(screen.queryByText('Required field')).toBeNull(); // helper text hidden when error exists
  });
  
  it('handles user input', async () => {
    const handleChange = vi.fn();
    render(<Input aria-label="input-field" onChange={handleChange} />);
    const input = screen.getByLabelText('input-field');
    await userEvent.type(input, 'test');
    expect(handleChange).toHaveBeenCalled();
  });
});
