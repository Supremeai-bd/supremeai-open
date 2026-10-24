import { describe, it, expect, beforeEach } from 'vitest';
import { useWorkspaceUiStateStore as useTierSStore } from './workspaceUiStateStore';
import type { Artifact, ReasoningStep } from './workspaceUiStateStore';

const reset = () =>
  useTierSStore.setState({
    shareDialogOpen: false,
    shareConversationId: null,
    reasoningSteps: [],
    isThinking: false,
    showReasoning: true,
    artifacts: [],
    activeArtifactId: null,
    artifactsPanelOpen: false,
    slashMenuOpen: false,
    slashFilter: '',
    slashPosition: { top: 0, left: 0 },
    searchDialogOpen: false,
    researchPanelOpen: false,
  });

describe('workspaceUiStateStore', () => {
  beforeEach(reset);

  it('opens and closes the share dialog', () => {
    useTierSStore.getState().openShareDialog('conv-1');
    expect(useTierSStore.getState().shareDialogOpen).toBe(true);
    expect(useTierSStore.getState().shareConversationId).toBe('conv-1');
    useTierSStore.getState().closeShareDialog();
    expect(useTierSStore.getState().shareDialogOpen).toBe(false);
    expect(useTierSStore.getState().shareConversationId).toBeNull();
  });

  it('manages reasoning steps and thinking state', () => {
    const steps: ReasoningStep[] = [{ content: 'step', score: 0.5, agent_id: 'a1' }];
    useTierSStore.getState().setReasoningSteps(steps);
    expect(useTierSStore.getState().reasoningSteps).toHaveLength(1);
    useTierSStore.getState().setIsThinking(true);
    expect(useTierSStore.getState().isThinking).toBe(true);
    useTierSStore.getState().toggleReasoning();
    expect(useTierSStore.getState().showReasoning).toBe(false);
  });

  it('adds, selects, removes and replaces artifacts', () => {
    const a1: Artifact = { id: 'a1', title: 'T', artifact_type: 'html', content: 'c', version: 1 };
    const a2: Artifact = { id: 'a2', title: 'T2', artifact_type: 'code', content: 'c2', version: 1 };
    useTierSStore.getState().addArtifact(a1);
    useTierSStore.getState().addArtifact(a2);
    expect(useTierSStore.getState().artifacts).toHaveLength(2);
    useTierSStore.getState().selectArtifact('a1');
    expect(useTierSStore.getState().activeArtifactId).toBe('a1');
    // adding with the same id replaces rather than duplicates
    useTierSStore.getState().addArtifact({ ...a1, version: 2 });
    expect(useTierSStore.getState().artifacts).toHaveLength(2);
    useTierSStore.getState().removeArtifact('a1');
    expect(useTierSStore.getState().artifacts).toHaveLength(1);
    expect(useTierSStore.getState().activeArtifactId).toBeNull();
  });

  it('toggles and sets the artifacts panel', () => {
    useTierSStore.getState().toggleArtifactsPanel();
    expect(useTierSStore.getState().artifactsPanelOpen).toBe(true);
    useTierSStore.getState().setArtifactsPanelOpen(false);
    expect(useTierSStore.getState().artifactsPanelOpen).toBe(false);
  });

  it('opens and closes the slash menu with filter and position', () => {
    useTierSStore.getState().openSlashMenu('he', { top: 10, left: 20 });
    expect(useTierSStore.getState().slashMenuOpen).toBe(true);
    expect(useTierSStore.getState().slashFilter).toBe('he');
    expect(useTierSStore.getState().slashPosition).toEqual({ top: 10, left: 20 });
    useTierSStore.getState().closeSlashMenu();
    expect(useTierSStore.getState().slashMenuOpen).toBe(false);
    expect(useTierSStore.getState().slashFilter).toBe('');
  });

  it('opens and closes the search dialog', () => {
    useTierSStore.getState().openSearchDialog();
    expect(useTierSStore.getState().searchDialogOpen).toBe(true);
    useTierSStore.getState().closeSearchDialog();
    expect(useTierSStore.getState().searchDialogOpen).toBe(false);
  });

  it('toggles and sets the research panel', () => {
    useTierSStore.getState().toggleResearchPanel();
    expect(useTierSStore.getState().researchPanelOpen).toBe(true);
    useTierSStore.getState().setResearchPanelOpen(false);
    expect(useTierSStore.getState().researchPanelOpen).toBe(false);
  });
});
