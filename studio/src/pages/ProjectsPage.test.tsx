import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../services/projectService', () => ({
  projectService: {
    listProjects: vi.fn(),
    createProject: vi.fn(),
    renameProject: vi.fn(),
    deleteProject: vi.fn(),
  },
}));

// বাংলা: WorkspaceLayout (UnifiedAppShell) ভারী — পেজ লজিক টেস্টে হালকা stub।
vi.mock('../components/layout/WorkspaceLayout', () => ({
  WorkspaceLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { ProjectsPage } from './ProjectsPage';
import { projectService } from '../services/projectService';

const mockedService = projectService as unknown as {
  listProjects: ReturnType<typeof vi.fn>;
  createProject: ReturnType<typeof vi.fn>;
  renameProject: ReturnType<typeof vi.fn>;
  deleteProject: ReturnType<typeof vi.fn>;
};

const renderPage = () =>
  render(
    <MemoryRouter>
      <ProjectsPage />
    </MemoryRouter>,
  );

describe('ProjectsPage (ERR-B01)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedService.listProjects.mockResolvedValue({ items: [], total: 0 });
  });

  it('shows the empty state with a working create button when there are no projects', async () => {
    renderPage();
    expect(await screen.findByTestId('projects-empty')).toBeInTheDocument();

    await userEvent.click(screen.getByTestId('create-project-btn'));
    expect(screen.getByTestId('project-modal')).toBeInTheDocument();
  });

  it('creates a project through the modal and refreshes the list', async () => {
    mockedService.createProject.mockResolvedValue({
      id: 'p9',
      name: 'Q4 Launch',
      description: '',
      status: 'active',
      created_at: null,
      updated_at: null,
    });
    mockedService.listProjects
      .mockResolvedValueOnce({ items: [], total: 0 })
      .mockResolvedValueOnce({
        items: [
          { id: 'p9', name: 'Q4 Launch', description: '', status: 'active', created_at: null },
        ],
        total: 1,
      });

    renderPage();
    await screen.findByTestId('projects-empty');

    await userEvent.click(screen.getByTestId('create-project-btn'));
    await userEvent.type(screen.getByTestId('project-name-input'), 'Q4 Launch');
    await userEvent.click(screen.getByTestId('project-submit-btn'));

    await waitFor(() => {
      expect(mockedService.createProject).toHaveBeenCalledWith({
        name: 'Q4 Launch',
        description: '',
      });
    });
    await waitFor(() => {
      expect(screen.getAllByTestId('project-card')).toHaveLength(1);
    });
    expect(screen.getByText('Q4 Launch')).toBeInTheDocument();
  });

  it('lists projects with rename and delete controls', async () => {
    mockedService.listProjects.mockResolvedValue({
      items: [
        {
          id: 'p1',
          name: 'Alpha',
          description: 'First space',
          status: 'active',
          created_at: '2026-09-16T00:00:00Z',
        },
      ],
      total: 1,
    });

    renderPage();
    expect(await screen.findByTestId('project-card')).toBeInTheDocument();
    expect(screen.getByText('Alpha')).toBeInTheDocument();
    expect(screen.getByTestId('project-delete-btn-p1')).toBeInTheDocument();
    expect(screen.getByTestId('project-rename-btn-p1')).toBeInTheDocument();
  });

  it('deletes a project after confirm and removes it from the list', async () => {
    mockedService.deleteProject.mockResolvedValue(undefined);
    mockedService.listProjects.mockResolvedValue({
      items: [
        {
          id: 'p1',
          name: 'Alpha',
          description: '',
          status: 'active',
          created_at: null,
        },
      ],
      total: 1,
    });

    renderPage();
    await screen.findByTestId('project-card');

    await userEvent.click(screen.getByTestId('project-delete-btn-p1'));
    await userEvent.click(screen.getByTestId('project-delete-confirm-btn-p1'));

    await waitFor(() => {
      expect(mockedService.deleteProject).toHaveBeenCalledWith('p1');
    });
    await waitFor(() => {
      expect(screen.queryByTestId('project-card')).not.toBeInTheDocument();
    });
  });

  it('shows an honest error state when loading fails', async () => {
    mockedService.listProjects.mockRejectedValue(new Error('network down'));
    renderPage();
    expect(await screen.findByTestId('projects-error')).toBeInTheDocument();
    expect(screen.getByText('network down')).toBeInTheDocument();
  });
});
