// ProjectsPage — real Project Spaces management (ERR-B01 fix)
// বাংলা মন্তব্য: /projects পেজটি আগে স্ট্যাটিক মার্কেটিং কার্ড ছিল (ERR-B01,
// canonical defect register 2026-09-15) — "Create a project space" ক্লিক কিছুই
// করত না। এখন real backend (/api/v1/projects)-এর সাথে যুক্ত: create modal,
// listing, rename এবং delete — loading/error/empty state সহ।

import { useState } from 'react';
import { ArrowRight, FolderKanban, Pencil, Plus, Sparkles, Trash2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { WorkspaceLayout } from '../components/layout/WorkspaceLayout';
import { useListResource } from '../hooks/useListResource';
import {
  projectService,
  type ProjectSpace,
} from '../services/projectService';

type ModalMode = { kind: 'create' } | { kind: 'rename'; project: ProjectSpace } | null;

function formatCreatedDate(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return iso;
  }
}

export function ProjectsPage() {
  // বাংলা (Wave 3 dedup): projects/isLoading/loadError + load + useEffect ক্লাস্টারটি
  // এখন useListResource হুকে; setItems দিয়ে delete-এর optimistic filter আগের মতোই।
  const {
    items: projects,
    isLoading,
    loadError,
    reload: loadProjects,
    setItems: setProjects,
  } = useListResource<ProjectSpace>({
    fetcher: async () => (await projectService.listProjects()).items,
  });
  const [modal, setModal] = useState<ModalMode>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const openCreateModal = () => {
    setName('');
    setDescription('');
    setSubmitError(null);
    setModal({ kind: 'create' });
  };

  const openRenameModal = (project: ProjectSpace) => {
    setName(project.name);
    setDescription(project.description);
    setSubmitError(null);
    setModal({ kind: 'rename', project });
  };

  const closeModal = () => {
    if (isSubmitting) return;
    setModal(null);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      setSubmitError('Project name is required.');
      return;
    }
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      if (modal?.kind === 'rename') {
        await projectService.renameProject(modal.project.id, name.trim());
      } else {
        await projectService.createProject({ name: name.trim(), description });
      }
      setModal(null);
      await loadProjects();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Request failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (projectId: string) => {
    setDeletingId(projectId);
    try {
      await projectService.deleteProject(projectId);
      setProjects((prev) => prev.filter((p) => p.id !== projectId));
    } catch {
      // Honest failure: reload so the UI reflects server truth.
      await loadProjects();
    } finally {
      setDeletingId(null);
      setConfirmDeleteId(null);
    }
  };

  return (
    <WorkspaceLayout>
      <div className="mx-auto w-full max-w-7xl px-5 py-8 text-[var(--sa-ink)] sm:px-8 lg:py-10">
        <header className="flex flex-col gap-4 border-b border-[var(--sa-border)] pb-8 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="sa-eyebrow">Build / Projects</p>
            <h1 className="mt-2 max-w-3xl text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
              A home for every outcome.
            </h1>
            <p className="mt-2 max-w-2xl text-[var(--sa-ink-muted)]">
              Keep agents, conversations, files, and decisions together so work
              compounds instead of disappearing.
            </p>
          </div>
          <button
            type="button"
            data-testid="create-project-btn"
            onClick={openCreateModal}
            className="inline-flex items-center justify-center gap-2 rounded-[var(--sa-radius-sm)] bg-[var(--sa-primary)] px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-90"
          >
            <Plus size={16} />
            Create a project space
          </button>
        </header>

        <section className="mt-8" aria-label="Project spaces">
          {isLoading ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="sa-surface-raised h-44 animate-pulse rounded-[var(--sa-radius-sm)]"
                  aria-hidden="true"
                />
              ))}
            </div>
          ) : loadError ? (
            <div
              role="alert"
              data-testid="projects-error"
              className="flex flex-col gap-3 border border-red-500/40 bg-red-500/5 p-4 text-sm sm:flex-row sm:items-center"
            >
              <span className="text-red-400">{loadError}</span>
              <button
                type="button"
                onClick={() => void loadProjects()}
                className="rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] px-3 py-1.5 font-medium transition hover:border-[var(--sa-primary)] sm:ml-auto"
              >
                Try again
              </button>
            </div>
          ) : projects.length === 0 ? (
            <div
              data-testid="projects-empty"
              className="sa-surface-raised flex flex-col items-center gap-3 p-10 text-center"
            >
              <div className="flex size-12 items-center justify-center rounded-xl bg-[var(--sa-primary-soft)] text-[var(--sa-primary)]">
                <FolderKanban size={22} />
              </div>
              <h2 className="text-lg font-semibold">No project spaces yet</h2>
              <p className="max-w-md text-sm text-[var(--sa-ink-muted)]">
                Start with a clear goal and shared context. Your first project
                space is one click away.
              </p>
              <button
                type="button"
                onClick={openCreateModal}
                className="mt-2 inline-flex items-center gap-2 rounded-[var(--sa-radius-sm)] bg-[var(--sa-primary)] px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-90"
              >
                <Plus size={16} />
                Create your first project space
              </button>
            </div>
          ) : (
            <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {projects.map((project) => (
                <li
                  key={project.id}
                  data-testid="project-card"
                  className="sa-surface-raised group flex min-h-44 flex-col justify-between p-5 transition hover:border-[var(--sa-primary)]"
                >
                  <div>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-[var(--sa-primary-soft)] text-[var(--sa-primary)]">
                        <FolderKanban size={17} />
                      </div>
                      <div className="flex items-center gap-1 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100">
                        <button
                          type="button"
                          data-testid={`project-rename-btn-${project.id}`}
                          aria-label={`Rename ${project.name}`}
                          onClick={() => openRenameModal(project)}
                          className="rounded-md p-1.5 text-[var(--sa-ink-muted)] transition hover:bg-[var(--sa-primary-soft)] hover:text-[var(--sa-primary)]"
                        >
                          <Pencil size={15} />
                        </button>
                        {confirmDeleteId === project.id ? (
                          <span className="flex items-center gap-1">
                            <button
                              type="button"
                              data-testid={`project-delete-confirm-btn-${project.id}`}
                              onClick={() => void handleDelete(project.id)}
                              disabled={deletingId === project.id}
                              className="rounded-md bg-red-500/10 px-2 py-1 text-xs font-semibold text-red-400 transition hover:bg-red-500/20 disabled:opacity-50"
                            >
                              {deletingId === project.id ? 'Deleting…' : 'Confirm'}
                            </button>
                            <button
                              type="button"
                              onClick={() => setConfirmDeleteId(null)}
                              className="rounded-md px-2 py-1 text-xs text-[var(--sa-ink-muted)] transition hover:text-[var(--sa-ink)]"
                            >
                              Cancel
                            </button>
                          </span>
                        ) : (
                          <button
                            type="button"
                            data-testid={`project-delete-btn-${project.id}`}
                            aria-label={`Delete ${project.name}`}
                            onClick={() => setConfirmDeleteId(project.id)}
                            className="rounded-md p-1.5 text-[var(--sa-ink-muted)] transition hover:bg-red-500/10 hover:text-red-400"
                          >
                            <Trash2 size={15} />
                          </button>
                        )}
                      </div>
                    </div>
                    <h2 className="mt-3 break-words font-medium">{project.name}</h2>
                    <p className="mt-1.5 line-clamp-3 text-sm leading-6 text-[var(--sa-ink-muted)]">
                      {project.description || 'No description yet.'}
                    </p>
                  </div>
                  <div className="mt-4 flex items-center justify-between border-t border-[var(--sa-border)] pt-3 text-xs text-[var(--sa-ink-muted)]">
                    <span>Created {formatCreatedDate(project.created_at)}</span>
                    <Link
                      to="/workspace/live"
                      className="inline-flex items-center gap-1 font-medium text-[var(--sa-primary)]"
                    >
                      Open <ArrowRight size={13} />
                    </Link>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <div className="mt-8 flex flex-col gap-3 border border-[var(--sa-border)] bg-[var(--sa-surface)] p-4 text-sm text-[var(--sa-ink-muted)] sm:flex-row sm:items-center">
          <Sparkles size={17} className="shrink-0 text-[var(--sa-primary)]" />
          <span>
            Every project space shares the same model, context, permission, and
            audit foundation.
          </span>
          <Link
            to="/workspace/live"
            className="inline-flex items-center gap-2 font-medium text-[var(--sa-primary)] sm:ml-auto"
          >
            Open Studio <ArrowRight size={15} />
          </Link>
        </div>
      </div>

      {modal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
          aria-label={modal.kind === 'rename' ? 'Rename project space' : 'Create a project space'}
          onClick={(e) => {
            if (e.target === e.currentTarget) closeModal();
          }}
        >
          <form
            onSubmit={(e) => void handleSubmit(e)}
            className="sa-surface-raised w-full max-w-md p-6"
            data-testid="project-modal"
          >
            <h2 className="text-lg font-semibold">
              {modal.kind === 'rename' ? 'Rename project space' : 'Create a project space'}
            </h2>
            <p className="mt-1 text-sm text-[var(--sa-ink-muted)]">
              {modal.kind === 'rename'
                ? 'Give this project space a clearer name.'
                : 'Start with a clear goal and shared context.'}
            </p>
            <label className="mt-5 block text-sm font-medium" htmlFor="project-name">
              Name
            </label>
            <input
              id="project-name"
              data-testid="project-name-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={200}
              autoFocus
              className="mt-1.5 w-full rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] bg-[var(--sa-canvas)] px-3 py-2.5 text-sm outline-none transition focus:border-[var(--sa-primary)]"
              placeholder="e.g. Q4 Launch"
            />
            {modal.kind === 'create' && (
              <>
                <label className="mt-4 block text-sm font-medium" htmlFor="project-description">
                  Description <span className="font-normal text-[var(--sa-ink-muted)]">(optional)</span>
                </label>
                <textarea
                  id="project-description"
                  data-testid="project-description-input"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  maxLength={5000}
                  rows={3}
                  className="mt-1.5 w-full resize-none rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] bg-[var(--sa-canvas)] px-3 py-2.5 text-sm outline-none transition focus:border-[var(--sa-primary)]"
                  placeholder="What is this space for?"
                />
              </>
            )}
            {submitError && (
              <p role="alert" data-testid="project-submit-error" className="mt-3 text-sm text-red-400">
                {submitError}
              </p>
            )}
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                onClick={closeModal}
                className="rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] px-4 py-2 text-sm font-medium transition hover:border-[var(--sa-primary)]"
              >
                Cancel
              </button>
              <button
                type="submit"
                data-testid="project-submit-btn"
                disabled={isSubmitting || !name.trim()}
                className="rounded-[var(--sa-radius-sm)] bg-[var(--sa-primary)] px-4 py-2 text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
              >
                {isSubmitting ? 'Saving…' : modal.kind === 'rename' ? 'Save' : 'Create'}
              </button>
            </div>
          </form>
        </div>
      )}
    </WorkspaceLayout>
  );
}

export default ProjectsPage;
