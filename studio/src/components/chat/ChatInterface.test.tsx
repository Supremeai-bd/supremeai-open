// বাংলা মন্তব্য (M10, issue #453): ChatInterface Tier-S হোস্ট ওয়্যারিং চুক্তি-টেস্ট।
// ১) কথোপকথন শুরুর আগে share/export সৎভাবে disabled — কোনো ভুয়া "current_conv" id নেই;
// ২) প্রথম মেসেজেই ক্লায়েন্ট-জেনারেটেড conversation_id প্রতিটি orchestration payload-এ
// যায় এবং পরের কলে একই id বজায় থাকে; ৩) S2 ThinkingPanel ও S3 ArtifactsPanel
// সত্যিই মাউন্ট/আনমাউন্ট হয়।
import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
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

  // M7 (issue #1518) বাংলা: আপলোড কলব্যাক আর no-op নয়। চুক্তি-টেস্ট:
  // ১) সফল XHR আপলোডে pending chip দেখা যায়; ২) পাঠানোর সময় অ্যাটাচমেন্ট
  // shared-types Attachment শেপে orchestration metadata-তে যায় (gateway
  // _chat_orchestrate metadata হুবহু ConversationCommand-এ পাস করে); ৩) ইউজার
  // মেসেজের metadata.attachments-এও থাকে; ৪) পাঠানোর পরে chips পরিষ্কার।
  it('wires image upload into pending chips and the orchestration metadata (M7)', async () => {
    // jsdom-এ XMLHttpRequest/URL.createObjectURL নেই — সফল আপলোড সিমুলেট।
    class FakeXHR {
      upload = { addEventListener: vi.fn() };
      private listeners: Record<string, (ev?: unknown) => void> = {};
      status = 200;
      responseText = JSON.stringify({
        id: 'att-1', url: 'https://cdn.example/x.png',
        name: 'x.png', size: 1234, mime_type: 'image/png',
      });
      addEventListener(ev: string, fn: (ev?: unknown) => void) { this.listeners[ev] = fn; }
      open() { /* no-op */ }
      setRequestHeader() { /* no-op */ }
      send() { this.listeners['load']?.(); }
    }
    vi.stubGlobal('XMLHttpRequest', FakeXHR);
    // বাংলা: jsdom-এ URL.createObjectURL/revokeObjectURL নেই — ম্যানুয়ালি
    // স্টাব করে finally-তে ফেরত দেওয়া হয় (vitest 3.x-এ vi.stubOnProperty নেই)।
    const originalCreateObjectURL = URL.createObjectURL;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    (URL as unknown as { createObjectURL: unknown }).createObjectURL = vi.fn(() => 'blob:fake-preview');
    (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = vi.fn();

    try {
      // বাংলা: আগের টেস্টে lang-toggle localStorage 'bn' করে রাখে — এই টেস্টে
      // EN placeholder নিশ্চিত করতে সেট।
      localStorage.setItem('sa_ui_lang', 'en');
      mockedExecute.mockResolvedValueOnce({ status: 'ok', response: 'reply' });
      render(<ChatInterface />);

      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      expect(fileInput).not.toBeNull();
      const file = new File(['pixels'], 'x.png', { type: 'image/png' });
      Object.defineProperty(fileInput, 'files', { value: [file] });
      fireEvent.change(fileInput);

      // আপলোড সফল → pending chip (থাম্বনেইল + রিমুভ বাটন) দেখা যায়
      // বাংলা: দুটি থাম্বনেইলই স্বাভাবিক — ImageUploadButton-এর নিজস্ব প্রিভিউ
      // (blob:) + composer-এর pending chip (ব্যাকএন্ড URL)।
      const chip = await screen.findByRole('listitem');
      expect(chip).toBeInTheDocument();
      expect(screen.getAllByAltText('x.png').length).toBeGreaterThan(0);

      await userEvent.type(screen.getByPlaceholderText(/type your message to the ai agent/i), 'What is this?');
      await userEvent.click(screen.getByRole('button', { name: /send/i }));
      await waitFor(() => expect(mockedExecute).toHaveBeenCalledTimes(1));

      const expectedAttachment = {
        id: 'att-1', type: 'image', name: 'x.png',
        url: 'https://cdn.example/x.png', size: 1234, mimeType: 'image/png',
      };
      const call = mockedExecute.mock.calls[0][0] as { payload: { metadata: { attachments?: unknown[] } } };
      // ২) orchestration metadata-তে অ্যাটাচমেন্ট যায়
      expect(call.payload.metadata.attachments).toEqual([expectedAttachment]);
      // ৩) ইউজার মেসেজ metadata-তেও থাকে (store-এ hasAttachments পথ)
      // বাংলা: at(-1) নয় — assistant রিপ্লাই পরে যোগ হয়; user মেসেজ খুঁজে নিই।
      const userMsg = useStore.getState().chatHistory.find(
        (m) => m.role === 'user' && m.content === 'What is this?',
      );
      expect(userMsg?.metadata?.attachments).toEqual([expectedAttachment]);
      // ৪) পাঠানোর পরে pending chips পরিষ্কার
      await waitFor(() => expect(screen.queryByRole('listitem')).toBeNull());
    } finally {
      vi.unstubAllGlobals();
      (URL as unknown as { createObjectURL: unknown }).createObjectURL = originalCreateObjectURL;
      (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = originalRevokeObjectURL;
    }
  });
});

// বাংলা মন্তব্য (M8, issue #1519): ভয়েস-ইনপুট ওয়্যারিং চুক্তি-টেস্ট।
// ১) SpeechRecognition-বিহীন ব্রাউজারে মাইক বোতাম সৎভাবে disabled (ভাঙা-বোতাম নয়);
// ২) স্টাব করা SR-এ ক্লিক → recognition.start() সত্যিই চলে, ফাইনাল ট্রান্সক্রিপ্ট
//    কম্পোজারে append হয় (overwrite নয় — দুইবার ফাইনাল = স্পেস-জোড়া),
//    interim ট্রান্সক্রিপ্ট placeholder-এ লাইভ দেখায়;
// ৩) STT lang চুক্তি: uiLang en → 'en-US', bn → 'bn-BD' — একক BCP-47 ট্যাগ;
//    পুরনো অবৈধ 'bn-BD, en-US' মান কম্পোজারে পৌঁছাতেই পারে না।
describe('ChatInterface M8 voice wiring contract (issue #1519)', () => {
  const win = window as unknown as { SpeechRecognition?: unknown };

  class FakeRecognition {
    lang = '';
    continuous = false;
    interimResults = false;
    started = false;
    stopped = false;
    aborted = false;
    onresult: ((e: unknown) => void) | null = null;
    onerror: ((e: unknown) => void) | null = null;
    onend: (() => void) | null = null;
    static instances: FakeRecognition[] = [];
    constructor() {
      FakeRecognition.instances.push(this);
    }
    start() {
      this.started = true;
    }
    stop() {
      this.stopped = true;
    }
    abort() {
      this.aborted = true;
    }
    // বাংলা: হুকের SpeechRecognitionEventLike শেপ অনুযায়ী ইভেন্ট তৈরি
    static finalEvent(text: string) {
      return {
        results: {
          0: { 0: { transcript: text }, isFinal: true },
          length: 1,
        },
      };
    }
    static interimEvent(text: string) {
      return {
        results: {
          0: { 0: { transcript: text }, isFinal: false },
          length: 1,
        },
      };
    }
  }

  afterEach(() => {
    delete win.SpeechRecognition;
    try {
      localStorage.removeItem('sa_ui_lang');
    } catch {
      /* noop */
    }
  });

  it('honestly disables the mic button when SpeechRecognition is unavailable', () => {
    localStorage.setItem('sa_ui_lang', 'en');
    render(<ChatInterface />);
    const mic = screen.getByTestId('chat-mic-button');
    expect(mic).toBeDisabled();
    // টুলটিপ থাকে — বোতাম নীরব-অদৃশ্য নয়
    expect(mic).toHaveAttribute('aria-label', 'Start voice input');
  });

  it('starts recognition on click and appends final transcript into the composer', () => {
    localStorage.setItem('sa_ui_lang', 'en');
    win.SpeechRecognition = FakeRecognition;
    render(<ChatInterface />);

    const mic = screen.getByTestId('chat-mic-button');
    expect(mic).not.toBeDisabled();
    fireEvent.click(mic);

    const inst = FakeRecognition.instances.at(-1);
    expect(inst).toBeDefined();
    expect(inst!.started).toBe(true);
    expect(inst!.lang).toBe('en-US');
    expect(inst!.continuous).toBe(false);
    expect(inst!.interimResults).toBe(true);

    // লাইভ interim ট্রান্সক্রিপ্ট placeholder-এ — ইনপুট state স্পর্শ করে না
    act(() => inst!.onresult!(FakeRecognition.interimEvent('হ্যালো')));
    // বাংলা: getByDisplayValue('') অন্য খালি ইনপুটেও ম্যাচ করে (অস্পষ্ট) —
    // placeholder-এ খোঁজা textarea-র .value সরাসরি দেখি।
    const ta = screen.getByPlaceholderText(/হ্যালো/) as HTMLTextAreaElement;
    expect(ta.value).toBe('');

    // ফাইনাল ১ + ফাইনাল ২ → append (স্পেস-জোড়া), overwrite নয়
    act(() => inst!.onresult!(FakeRecognition.finalEvent('প্রথম কথা')));
    act(() => inst!.onresult!(FakeRecognition.finalEvent('দ্বিতীয় কথা')));
    expect(screen.getByDisplayValue('প্রথম কথা দ্বিতীয় কথা')).toBeInTheDocument();
  });

  it('uses bn-BD for STT when the UI language is Bangla', () => {
    localStorage.setItem('sa_ui_lang', 'bn');
    win.SpeechRecognition = FakeRecognition;
    render(<ChatInterface />);

    const inst = FakeRecognition.instances.at(-1);
    expect(inst!.lang).toBe('bn-BD');
    // বাংলা UI-তে মাইক টুলটিপও বাংলা
    expect(screen.getByTestId('chat-mic-button')).toHaveAttribute(
      'aria-label',
      'ভয়েস ইনপুট শুরু করুন',
    );
  });
});
