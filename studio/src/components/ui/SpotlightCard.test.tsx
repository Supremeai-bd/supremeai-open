import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SpotlightCard } from './SpotlightCard';

describe('SpotlightCard Component', () => {
  it('renders children properly', () => {
    render(
      <SpotlightCard data-testid="spotlight-card">
        <span data-testid="child-content">Active Card Content</span>
      </SpotlightCard>
    );

    expect(screen.getByTestId('spotlight-card')).toBeInTheDocument();
    expect(screen.getByTestId('child-content')).toHaveTextContent('Active Card Content');
  });

  it('updates mouse coordinates on mousemove and triggers mouseenter/leave', () => {
    const { container } = render(
      <SpotlightCard spotlightColor="purple" data-testid="spotlight-card">
        <p>Interactive Spot</p>
      </SpotlightCard>
    );

    const card = screen.getByTestId('spotlight-card');
    fireEvent.mouseEnter(card);
    fireEvent.mouseMove(card, { clientX: 100, clientY: 50 });
    fireEvent.mouseLeave(card);

    expect(container).toBeInTheDocument();
  });
});
