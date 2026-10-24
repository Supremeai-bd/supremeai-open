import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EmptyState } from './EmptyState';

describe('EmptyState Component', () => {
  it('renders title, description and CTA buttons', () => {
    const handleAction = vi.fn();
    const handleSecondary = vi.fn();

    render(
      <EmptyState
        title="No Active Projects"
        description="You have not created any projects yet. Start by generating code."
        actionLabel="Create Project"
        onAction={handleAction}
        secondaryActionLabel="Explore Templates"
        onSecondaryAction={handleSecondary}
      />
    );

    expect(screen.getByText('No Active Projects')).toBeInTheDocument();
    expect(screen.getByText(/You have not created any projects yet/i)).toBeInTheDocument();
    
    const primaryBtn = screen.getByText('Create Project');
    fireEvent.click(primaryBtn);
    expect(handleAction).toHaveBeenCalledOnce();

    const secondaryBtn = screen.getByText('Explore Templates');
    fireEvent.click(secondaryBtn);
    expect(handleSecondary).toHaveBeenCalledOnce();
  });
});
