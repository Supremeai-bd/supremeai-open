import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { UserDashboard } from './UserDashboard';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
  },
});

const renderWithProviders = (ui: React.ReactElement) =>
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );

const mockedUseNavigate = vi.fn();
const mockUseAuthStore = vi.fn();

vi.mock('react-router-dom', () => ({
  MemoryRouter: ({ children }: { children: React.ReactNode }) => children,
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => <a href={to}>{children}</a>,
  useNavigate: () => mockedUseNavigate,
}));

vi.mock('../../store/authStore', () => ({
  useAuthStore: () => mockUseAuthStore(),
}));

describe('UserDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuthStore.mockReturnValue({ user: { name: 'TestUser' } });
  });

  it('renders the calm intent-first workspace', () => {
    renderWithProviders(<UserDashboard />);
    expect(screen.getByText('Good morning, TestUser.')).toBeInTheDocument();
    expect(screen.getByText('What would you like to do?')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Ask a question, describe a task, or share an idea...')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Personalize/i })).toBeInTheDocument();
  });

  it('uses a neutral greeting when no user name is available', () => {
    mockUseAuthStore.mockReturnValue({ user: null });
    renderWithProviders(<UserDashboard />);
    expect(screen.getByText('Good morning, there.')).toBeInTheDocument();
  });

  it('opens Studio from the intent input carrying the typed intent', () => {
    renderWithProviders(<UserDashboard />);
    const input = screen.getByPlaceholderText('Ask a question, describe a task, or share an idea...');
    fireEvent.change(input, { target: { value: 'build me a landing page' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    // FIX(intent-carryover): Enter forwards the typed intent as a URL param
    expect(mockedUseNavigate).toHaveBeenCalledWith(
      `/workspace/live?intent=${encodeURIComponent('build me a landing page')}`
    );
  });

  it('does not open Studio for composing or unrelated keys', () => {
    renderWithProviders(<UserDashboard />);
    const input = screen.getByPlaceholderText('Ask a question, describe a task, or share an idea...');
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(mockedUseNavigate).not.toHaveBeenCalled();
  });

  it('renders quick-action chips and navigates with intent param on click', () => {
    renderWithProviders(<UserDashboard />);
    const chipsContainer = screen.getByTestId('intent-chips');
    expect(chipsContainer).toBeInTheDocument();
    const firstChip = chipsContainer.querySelector('button');
    expect(firstChip).not.toBeNull();
    if (firstChip) {
      fireEvent.click(firstChip);
      expect(mockedUseNavigate).toHaveBeenCalledWith(
        expect.stringContaining('/workspace/live?intent=')
      );
    }
  });

  it('renders the main workspace sections and actions', () => {
    renderWithProviders(<UserDashboard />);
    expect(screen.getByText('Recent work')).toBeInTheDocument();
    expect(screen.getByText('Your tools')).toBeInTheDocument();
    expect(screen.getByText('Only what you need')).toBeInTheDocument();
    expect(screen.getByText('Nothing here yet')).toBeInTheDocument();
    expect(screen.getByText('Need a starting point?')).toBeInTheDocument();
  });
});
