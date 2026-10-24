import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ToastStack } from './ToastStack';

describe('ToastStack', () => {
  it('renders toast title and message', () => {
    render(
      <ToastStack
        toasts={[{ id: '1', type: 'success', title: 'Done', message: 'ok' }]}
        onDismiss={vi.fn()}
      />
    );
    expect(screen.getByText('Done')).toBeInTheDocument();
    expect(screen.getByText('ok')).toBeInTheDocument();
  });

  it('renders multiple toasts', () => {
    render(
      <ToastStack
        toasts={[
          { id: '1', type: 'info', title: 'A' },
          { id: '2', type: 'error', title: 'B' },
        ]}
        onDismiss={vi.fn()}
      />
    );
    expect(screen.getByText('A')).toBeInTheDocument();
    expect(screen.getByText('B')).toBeInTheDocument();
  });

  it('calls onDismiss with toast id', () => {
    const onDismiss = vi.fn();
    render(
      <ToastStack
        toasts={[{ id: '42', type: 'warning', title: 'Warn' }]}
        onDismiss={onDismiss}
      />
    );
    fireEvent.click(screen.getByRole('button'));
    expect(onDismiss).toHaveBeenCalledWith('42');
  });

  it('applies security tone class', () => {
    const { container } = render(
      <ToastStack toasts={[{ id: '1', type: 'security', title: 'Sec' }]} onDismiss={vi.fn()} />
    );
    expect(container.querySelector('.text-\\[\\#bc13fe\\]')).toBeTruthy();
  });
});
