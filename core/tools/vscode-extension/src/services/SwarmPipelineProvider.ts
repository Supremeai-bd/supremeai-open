import * as vscode from 'vscode';
import axios from 'axios';
import { detectSwarmAgents, notifySwarmState, SwarmState } from '../agentDetector';

const OUTPUT_CHANNEL = 'SupremeAI Agent Review Workflow';

function getBackendUrl(): string {
  const cfg = vscode.workspace.getConfiguration('supremeai');
  // FE-11 (Issue #526): NEVER silently default to a loopback URL. This ships as
  // a published extension — falling back to http://localhost:8080 made every
  // request fail invisibly against nothing-listening on the user's machine.
  // Unconfigured = empty string; the caller surfaces an actionable error and
  // the offline-first local fallback still runs.
  return (cfg.get<string>('swarmBackendUrl') || cfg.get<string>('backendUrl') || '').trim();
}

/**
 * Calls the verified Trio backend (POST /api/v1/ide-trio/execute) which runs
 * GeminiWriter -> KiloReviewer -> ClineChecker. This backend is the execution
 * engine for the 3-agent swarm (Trio) instantiation; larger swarms route here
 * too, with the agent list/mode passed through for orchestration.
 */
async function runBackendPipeline(
  prompt: string,
  state: SwarmState
): Promise<{ ok: boolean; notes: string[]; raw?: unknown }> {
  const notes: string[] = [];
  try {
    const base = getBackendUrl();
    if (!base) {
      // FE-11 (Issue #526): actionable 'not configured' error — never loopback.
      notes.push(
        'Swarm backend not configured - set supremeai.swarmBackendUrl (or supremeai.backendUrl) in Settings. Using local fallback.'
      );
      void vscode.window
        .showErrorMessage('SupremeAI: swarm backend not configured', 'Open Settings')
        .then((action) => {
          if (action === 'Open Settings') {
            void vscode.commands.executeCommand('workbench.action.openSettings', 'supremeai.swarmBackendUrl');
          }
        });
      return { ok: false, notes };
    }
    const res = await axios.post<{ ok?: boolean; notes?: unknown; result?: unknown }>(
      `${base}/api/v1/agent_review_workflow/execute`,
      { prompt, ide: state.ide, agents: state.agents, mode: state.mode },
      { timeout: 90000 }
    );
    const data = res.data;
    const extra = Array.isArray(data.notes) ? (data.notes as string[]) : [];
    return { ok: data.ok !== false, notes: extra, raw: data.result ?? data };
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    notes.push(`Backend unreachable (${msg}) - falling back to local review.`);
    return { ok: false, notes };
  }
}

/** Offline-first local fallback: rule-based review + production checks. */
async function runLocalFallback(
  prompt: string,
  state: SwarmState
): Promise<{ notes: string[] }> {
  const notes: string[] = [];
  if (!state.hasGemini) notes.push('Gemini (Writer) not detected - using SupremeAI Core.');
  if (!state.hasKilo) notes.push('Kilo (Reviewer) not detected - local rule-based review.');
  if (!state.hasCline) notes.push('Cline (Checker) not detected - local production checks.');
  notes.push(`Task: ${prompt}`);
  notes.push('Backend unreachable - local fallback complete.');
  return { notes };
}

function showOutput(title: string, lines: string[]): void {
  const ch = vscode.window.createOutputChannel(OUTPUT_CHANNEL);
  ch.clear();
  ch.appendLine(`=== ${title} ===`);
  lines.forEach((l) => ch.appendLine(l));
  ch.show(true);
}

async function executeSwarm(): Promise<void> {
  const state = detectSwarmAgents();
  notifySwarmState(state);

  const prompt = await vscode.window.showInputBox({
    prompt: 'SupremeAI Agent Review Workflow task',
    placeHolder: 'e.g. Build a FastAPI health endpoint returning {"status":"ok"}',
    ignoreFocusOut: true,
  });
  if (!prompt) return;

  const baseNotes = [
    `IDE: ${state.ide} | Mode: ${state.mode} | Detected: ${state.agents.map((a) => a.displayName).join(', ')}`,
    `Trio ready: ${state.trioReady ? 'YES (Gemini+Kilo+Cline)' : 'NO - proceeding with available agents'}`,
  ];

  const run = await runBackendPipeline(prompt, state);
  if (!run.ok) {
    const fb = await runLocalFallback(prompt, state);
    showOutput('SupremeAI Agent Review Workflow (Local Fallback)', [...baseNotes, ...fb.notes]);
    return;
  }

  showOutput('SupremeAI Agent Review Workflow Result', [
    ...baseNotes,
    ...run.notes,
    ...(run.raw ? [JSON.stringify(run.raw, null, 2)] : []),
  ]);
}

export function registerSwarmCommands(context: vscode.ExtensionContext): void {
  context.subscriptions.push(
    vscode.commands.registerCommand('supremeai.swarmPipeline', executeSwarm),
    // Backward-compatible alias: Trio = the 3-agent swarm instantiation (Gemini+Kilo+Cline).
    vscode.commands.registerCommand('supremeai.trioPipeline', executeSwarm)
  );
}
