import { create } from 'zustand';

// ─── Types ───────────────────────────────────────────────────────────────

export interface ReasoningStep {
  content: string;
  score?: number;
  agent_id?: string;
}

export interface Artifact {
  id: string;
  title: string;
  artifact_type: 'html' | 'react' | 'svg' | 'mermaid' | 'code';
  content: string;
  version: number;
}

export interface WorkspaceUiState {
  // S1: Share
  shareDialogOpen: boolean;
  shareConversationId: string | null;
  openShareDialog: (convId: string) => void;
  closeShareDialog: () => void;

  // S2: Reasoning
  reasoningSteps: ReasoningStep[];
  isThinking: boolean;
  showReasoning: boolean;
  setReasoningSteps: (steps: ReasoningStep[]) => void;
  setIsThinking: (thinking: boolean) => void;
  toggleReasoning: () => void;

  // S3: Artifacts
  artifacts: Artifact[];
  activeArtifactId: string | null;
  artifactsPanelOpen: boolean;
  setArtifacts: (artifacts: Artifact[]) => void;
  addArtifact: (artifact: Artifact) => void;
  removeArtifact: (id: string) => void;
  selectArtifact: (id: string | null) => void;
  toggleArtifactsPanel: () => void;
  setArtifactsPanelOpen: (open: boolean) => void;

  // S5: Slash Commands
  slashMenuOpen: boolean;
  slashFilter: string;
  slashPosition: { top: number; left: number };
  openSlashMenu: (filter: string, pos: { top: number; left: number }) => void;
  closeSlashMenu: () => void;

  // S6: Search
  searchDialogOpen: boolean;
  openSearchDialog: () => void;
  closeSearchDialog: () => void;

  // S12: Deep Research
  researchPanelOpen: boolean;
  toggleResearchPanel: () => void;
  setResearchPanelOpen: (open: boolean) => void;
}

// ─── Store ───────────────────────────────────────────────────────────────

export const useWorkspaceUiStateStore = create<WorkspaceUiState>((set) => ({
  // ── S1: Share ──────────────────────────────────────────────
  shareDialogOpen: false,
  shareConversationId: null,
  openShareDialog: (convId: string) =>
    set({
      shareDialogOpen: true,
      shareConversationId: convId,
    }),
  closeShareDialog: () =>
    set({
      shareDialogOpen: false,
      shareConversationId: null,
    }),

  // ── S2: Reasoning ─────────────────────────────────────────
  reasoningSteps: [],
  isThinking: false,
  showReasoning: true,
  setReasoningSteps: (steps: ReasoningStep[]) =>
    set({ reasoningSteps: steps }),
  setIsThinking: (thinking: boolean) =>
    set({ isThinking: thinking }),
  toggleReasoning: () =>
    set((state) => ({ showReasoning: !state.showReasoning })),

  // ── S3: Artifacts ──────────────────────────────────────────
  artifacts: [],
  activeArtifactId: null,
  artifactsPanelOpen: false,
  setArtifacts: (artifacts: Artifact[]) =>
    set({ artifacts }),
  addArtifact: (artifact: Artifact) =>
    set((state) => {
      const exists = state.artifacts.findIndex((a) => a.id === artifact.id);
      if (exists >= 0) {
        const updated = [...state.artifacts];
        updated[exists] = artifact;
        return { artifacts: updated };
      }
      return { artifacts: [...state.artifacts, artifact] };
    }),
  removeArtifact: (id: string) =>
    set((state) => ({
      artifacts: state.artifacts.filter((a) => a.id !== id),
      activeArtifactId: state.activeArtifactId === id ? null : state.activeArtifactId,
    })),
  selectArtifact: (id: string | null) =>
    set({ activeArtifactId: id }),
  toggleArtifactsPanel: () =>
    set((state) => ({ artifactsPanelOpen: !state.artifactsPanelOpen })),
  setArtifactsPanelOpen: (open: boolean) =>
    set({ artifactsPanelOpen: open }),

  // ── S5: Slash Commands ─────────────────────────────────────
  slashMenuOpen: false,
  slashFilter: '',
  slashPosition: { top: 0, left: 0 },
  openSlashMenu: (filter: string, pos: { top: number; left: number }) =>
    set({
      slashMenuOpen: true,
      slashFilter: filter,
      slashPosition: pos,
    }),
  closeSlashMenu: () =>
    set({
      slashMenuOpen: false,
      slashFilter: '',
    }),

  // ── S6: Search ─────────────────────────────────────────────
  searchDialogOpen: false,
  openSearchDialog: () =>
    set({ searchDialogOpen: true }),
  closeSearchDialog: () =>
    set({ searchDialogOpen: false }),

  // ── S12: Deep Research ─────────────────────────────────────
  researchPanelOpen: false,
  toggleResearchPanel: () =>
    set((state) => ({ researchPanelOpen: !state.researchPanelOpen })),
  setResearchPanelOpen: (open: boolean) =>
    set({ researchPanelOpen: open }),
}));

// Backward-compatibility alias during phased refactoring
export const useTierSStore = useWorkspaceUiStateStore;

