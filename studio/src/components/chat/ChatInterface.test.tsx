// বাংলা মন্তব্য (M10, issue #453): ChatInterface Tier-S হোস্ট ওয়্যারিং চুক্তি-টেস্ট।
// ১) কথোপকথন শুরুর আগে share/export সৎভাবে disabled — কোনো ভুয়া "current_conv" id নেই;
// ২) প্রথম মেসেজেই ক্লায়েন্ট-জেনারেটেড conversation_id প্রতিটি orchestration payload-এ
// যায় এবং পরের কলে একই id বজায় থাকে; ৩) S2 ThinkingPanel ও S3 ArtifactsPanel
// সত্যিই মাউন্ট/আনমাউন্ট হয়।
import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// বাংলা: jsdom scrollIntoView বাস্তবায়ন করে না — UnifiedChatBubble/ChatInterface
// স্ক্রল ইফেক্টে এটি ব্যবহার করে।
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

vi.mock('../../services/controlPlane', () => ({
  controlPlane: { executeCapability: vi.fn() },
}));

// বাংলা: ShareDialog/ExportMenu ভেতরে apiClient ব্যবহার করে — নেটওয়ার্ক মক।
vi.mock('../../services/apiClient', () => ({
  apiClient: { get: vi.fn().mockResolvedValue([]), post: vi.fn(), put: vi.fn(), del: vi.fn() },
}));

import { ChatInterface } from './ChatInterface';
import { controlPlane } from '../../services/controlPlane';
import { useStore } from '../../store/useStore';
import { useWorkspaceUiStateStore } from '../../store/workspaceUiStateStore';

const mockedExecute = controlPlane.executeCapability as ReturnType<typeof vi.fn>;

function resetStores() {
  useStore.setState({ chatHistory: [], isOrchestrating: false });
  useWorkspaceUiStateStore.setState({
    shareDialogOpen: false,
    shareConversationId: null,
    reasoningSteps: [],
    isThinking: false,
    showReasoning: true,
    artifacts: [],
    activeArtifactId: null,
    artifactsPanelOpen: false,
    slashMenuOpen: false,
    searchDialogOpen: false,
  });
}

describe('ChatInterface Tier-S wiring contract (M10)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetStores();
  });

  it('keeps share and export honestly disabled before a real conversation exists', () => {
    render(<ChatInterface />);
    const gated = screen.getAllByTitle('Start a conversation first');
    expect(gated.length).toBe(2); // share button + export placeholder
    gated.forEach((btn) => expect(btn).toBeDisabled());
    // কোনো ভুয়া "current_conv" টুলটিপ বা id কোথাও থাকতে পারে না
    expect(screen.queryByTitle('Share Conversation')).toBeNull();
  });

  it('generates a real client conversation_id, sends it, and keeps it stable', async () => {
    mockedExecute.mockResolvedValueOnce({ status: 'ok', response: 'Hello there' });
    render(<ChatInterface />);

    const input = screen.getByPlaceholderText(/type your message to the ai agent/i);
    await userEvent.type(input, 'Hello agent');
    await userEvent.click(screen.getByRole('button', { name: /send/i }));

    await waitFor(() => expect(mockedExecute).toHaveBeenCalledTimes(1));
    const firstCall = mockedExecute.mock.calls[0][0] as {
      payload: { conversation_id: string; prompt: string };
    };
    expect(firstCall.payload.conversation_id).toEqual(expect.any(String));
    expect(firstCall.payload.conversation_id).not.toBe('current_conv');
    expect(firstCall.payload.prompt).toBe('Hello agent');

    // পরবর্তী কলে একই conversation_id বজায় থাকে (persistent identity)
    mockedExecute.mockResolvedValueOnce({ status: 'ok', response: 'Again' });
    await userEvent.type(screen.getByPlaceholderText(/type your message to the ai agent/i), 'Second message');
    await userEvent.click(screen.getByRole('button', { name: /send/i }));
    await waitFor(() => expect(mockedExecute).toHaveBeenCalledTimes(2));
    const secondCall = mockedExecute.mock.calls[1][0] as {
      payload: { conversation_id: string };
    };
    expect(secondCall.payload.conversation_id).toBe(firstCall.payload.conversation_id);
  });

  it('enables share with the real conversation id after messaging', async () => {
    mockedExecute.mockResolvedValue({ status: 'ok', response: 'reply' });
    render(<ChatInterface />);

    await userEvent.type(screen.getByPlaceholderText(/type your message to the ai agent/i), 'Start talking');
    await userEvent.click(screen.getByRole('button', { name: /send/i }));
    await waitFor(() => expect(screen.getByTitle('Share Conversation')).toBeEnabled());

    // export placeholder সরে গেছে — সত্যিকার ExportMenu এসেছে
    expect(screen.queryAllByTitle('Start a conversation first')).toHaveLength(0);
  });

  it('mounts and unmounts the S2 ThinkingPanel via toolbar toggle', async () => {
    useWorkspaceUiStateStore.setState({
      reasoningSteps: [{ content: 'Step A', score: 0.9 }],
    });
    render(<ChatInterface />);

    // showReasoning default true + ধাপ আছে → প্যানেল দৃশ্যমান
    expect(screen.getByText(/Reasoning \(1 step\)/)).toBeInTheDocument();

    await userEvent.click(screen.getByTitle('Toggle reasoning panel'));
    expect(screen.queryByText(/Reasoning \(1 step\)/)).toBeNull();
  });

  it('mounts and unmounts the S3 ArtifactsPanel via toolbar toggle', async () => {
    useWorkspaceUiStateStore.setState({
      artifactsPanelOpen: true,
      artifacts: [
        { id: 'a1', title: 'Demo', artifact_type: 'code', content: 'const x = 1;', version: 1 },
      ],
    });
    render(<ChatInterface />);

    expect(screen.getByTestId('artifacts-panel-container')).toBeInTheDocument();
    expect(screen.getByText('Demo')).toBeInTheDocument();

    await userEvent.click(screen.getByTitle('Toggle artifacts panel'));
    expect(screen.queryByTestId('artifacts-panel-container')).toBeNull();
  });

  it('renders quick action chips and pre-fills composer on click', async () => {
    render(<ChatInterface />);
    const chips = screen.getByTestId('chat-chips');
    expect(chips).toBeInTheDocument();
    expect(screen.getByText('Audit my project')).toBeInTheDocument();

    await userEvent.click(screen.getByText('Audit my project'));
    const input = screen.getByPlaceholderText(/type your message to the ai agent/i) as HTMLTextAreaElement;
    expect(input.value).toBe('Audit my project');
  });

  it('toggles UI language when clicking the language toggle', async () => {
    render(<ChatInterface />);
    const langBtn = screen.getByTestId('lang-toggle');
    expect(langBtn).toHaveTextContent('EN');

    await userEvent.click(langBtn);
    expect(langBtn).toHaveTextContent('বাং');
    expect(screen.getByPlaceholderText(/এআই এজেন্টকে আপনার মেসেজ লিখুন/i)).toBeInTheDocument();
  });
});
