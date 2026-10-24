import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ProtectedRoute, GuestRoute, AuthLoadingSpinner } from './AuthGuards';

const mockAuthState = {
  loggedIn: { status: 'loggedIn', initialize: vi.fn().mockResolvedValue(undefined) },
  loggedOut: { status: 'loggedOut', initialize: vi.fn().mockResolvedValue(undefined) },
  uninitialized: { status: 'uninitialized', initialize: vi.fn().mockResolvedValue(undefined) },
};

vi.mock('../../store/authStore', () => {
  // identity.ts canAccessAdminContext() reads the store non-reactively via
  // useAuthStore.getState() — the mock must expose the same zustand surface.
  const useAuthStoreMock = (selector?: (state: typeof mockAuthState['loggedIn']) => unknown) => {
    const state = mockAuthState['loggedIn'];
    return selector ? selector(state) : state;
  };
  (useAuthStoreMock as unknown as { getState: () => typeof mockAuthState['loggedIn'] }).getState =
    () => mockAuthState['loggedIn'];
  return {
    useAuthStore: useAuthStoreMock,
    AuthStatus: { UNINITIALIZED: 'uninitialized', LOGGED_OUT: 'loggedOut', LOGGED_IN: 'loggedIn' },
  };
});

describe('AuthGuards', () => {
  beforeEach(() => {
    Object.assign(mockAuthState['loggedIn'], { status: 'loggedIn', initialize: vi.fn().mockResolvedValue(undefined) });
    Object.assign(mockAuthState['loggedOut'], { status: 'loggedOut', initialize: vi.fn().mockResolvedValue(undefined) });
    Object.assign(mockAuthState['uninitialized'], { status: 'uninitialized', initialize: vi.fn().mockResolvedValue(undefined) });
  });

  describe('AuthLoadingSpinner', () => {
    it('renders the loading indicator', () => {
      render(<AuthLoadingSpinner />);
      expect(screen.getByText('Authenticating...')).toBeInTheDocument();
    });
  });

  describe('ProtectedRoute', () => {
    it('renders children when authenticated', () => {
      render(
        <MemoryRouter initialEntries={['/']}>
          <Routes>
            <Route path="/" element={<ProtectedRoute><div>Secret</div></ProtectedRoute>} />
          </Routes>
        </MemoryRouter>
      );
      expect(screen.getByText('Secret')).toBeInTheDocument();
    });

    it('renders the loading spinner when checking auth', () => {
      Object.assign(mockAuthState['loggedIn'], { status: 'uninitialized', initialize: vi.fn().mockResolvedValue(undefined) });
      render(
        <MemoryRouter initialEntries={['/']}>
          <Routes>
            <Route path="/" element={<ProtectedRoute><div>Secret</div></ProtectedRoute>} />
          </Routes>
        </MemoryRouter>
      );
      expect(screen.getByText('Authenticating...')).toBeInTheDocument();
    });

    it('renders nothing when not authenticated', () => {
      Object.assign(mockAuthState['loggedIn'], { status: 'loggedOut', initialize: vi.fn().mockResolvedValue(undefined) });
      const { container } = render(
        <MemoryRouter initialEntries={['/']}>
          <Routes>
            <Route path="/" element={<ProtectedRoute><div>Secret</div></ProtectedRoute>} />
          </Routes>
        </MemoryRouter>
      );
      expect(container.innerHTML).toBe('');
    });
  });

  describe('GuestRoute', () => {
    it('renders children when not authenticated', () => {
      Object.assign(mockAuthState['loggedIn'], { status: 'loggedOut', initialize: vi.fn().mockResolvedValue(undefined) });
      render(
        <MemoryRouter initialEntries={['/']}>
          <Routes>
            <Route path="/" element={<GuestRoute><div>Public</div></GuestRoute>} />
          </Routes>
        </MemoryRouter>
      );
      expect(screen.getByText('Public')).toBeInTheDocument();
    });

    it('renders nothing when authenticated', () => {
      const { container } = render(
        <MemoryRouter initialEntries={['/']}>
          <Routes>
            <Route path="/" element={<GuestRoute><div>Public</div></GuestRoute>} />
          </Routes>
        </MemoryRouter>
      );
      expect(container.innerHTML).toBe('');
    });
  });
});
