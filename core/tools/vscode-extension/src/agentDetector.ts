import * as vscode from 'vscode';

/**
 * SupremeAI IDE Swarm / Trio detector.
 * Detects the host IDE + every AI agent installed on the device, then picks the
 * matching collective-intelligence mode:
 *   0 external agents  -> 'standalone'  (SupremeAI Core alone)
 *   1-2 agents         -> 'duo'         (SupremeAI + one companion)
 *   >=3 agents         -> 'swarm'       (full collective; Trio = 3-agent swarm)
 *
 * Antigravity IDE ships Gemini *built-in* (not as an extension), so the IDE
 * itself is detected via appName/uriScheme and counted as the 'gemini' writer.
 */

export type IdeType = 'antigravity' | 'vscode' | 'cursor' | 'windsurf' | 'webstorm' | 'unknown';
export type AgentType =
  | 'gemini'
  | 'kilo'
  | 'cline'
  | 'copilot'
  | 'copilot-chat'
  | 'tabnine'
  | 'cody'
  | 'blackbox'
  | 'aws'
  | 'other';

export interface DetectedAgent {
  id: string;
  displayName: string;
  type: AgentType;
  role: 'writer' | 'reviewer' | 'checker' | 'other';
}

export type SwarmMode = 'standalone' | 'duo' | 'swarm';

export interface SwarmState {
  ide: IdeType;
  agents: DetectedAgent[];
  mode: SwarmMode;
  agentCount: number;
  hasGemini: boolean;
  hasKilo: boolean;
  hasCline: boolean;
  trioReady: boolean; // true when {Gemini + Kilo + Cline} are all available (Trio = 3-agent swarm)
}

/** Antigravity IDE (Google Gemini-native VS Code fork) - built-in Gemini, no ext needed. */
export function isAntigravity(): boolean {
  const app = vscode.env.appName?.toLowerCase() || '';
  const scheme = vscode.env.uriScheme?.toLowerCase() || '';
  return app.includes('antigravity') || scheme.includes('antigravity');
}

export function detectIde(): IdeType {
  const app = (vscode.env.appName || '').toLowerCase();
  if (app.includes('antigravity')) return 'antigravity';
  if (app.includes('cursor')) return 'cursor';
  if (app.includes('windsurf')) return 'windsurf';
  if (app.includes('webstorm')) return 'webstorm';
  if (app.includes('vscode')) return 'vscode';
  return 'unknown';
}

const KNOWN_AI_AGENTS: { id: string; type: AgentType; displayName: string }[] = [
  { id: 'kilocode.kilo-code', type: 'kilo', displayName: 'Kilo Code' },
  { id: 'kilo-code.kilo-code', type: 'kilo', displayName: 'Kilo Code (alt id)' },
  { id: 'saoudrizwan.claude-dev', type: 'cline', displayName: 'Cline (Claude Dev)' },
  { id: 'cline.cline', type: 'cline', displayName: 'Cline' },
  { id: 'github.copilot', type: 'copilot', displayName: 'GitHub Copilot' },
  { id: 'github.copilot-chat', type: 'copilot-chat', displayName: 'GitHub Copilot Chat' },
  { id: 'tabnine.tabnine-vscode', type: 'tabnine', displayName: 'Tabnine' },
  { id: 'sourcegraph.cody-ai', type: 'cody', displayName: 'Cody' },
  { id: 'blackboxapp.blackbox', type: 'blackbox', displayName: 'Blackbox' },
  { id: 'amazon.aws-toolkit-vscode', type: 'aws', displayName: 'AWS Toolkit' },
];

function roleFor(type: AgentType): DetectedAgent['role'] {
  switch (type) {
    case 'gemini':
      return 'writer';
    case 'kilo':
      return 'reviewer';
    case 'cline':
      return 'checker';
    default:
      return 'other';
  }
}

/** Full swarm detection: IDE + every AI agent installed on the device. */
export function detectSwarmAgents(): SwarmState {
  const ide = detectIde();
  const antigravity = ide === 'antigravity';
  const agents: DetectedAgent[] = [];

  // Antigravity IDE ships Gemini built-in -> counts as the writer.
  if (antigravity) {
    agents.push({
      id: 'antigravity.gemini',
      displayName: 'Antigravity IDE (Gemini built-in)',
      type: 'gemini',
      role: 'writer',
    });
  }

  KNOWN_AI_AGENTS.forEach(({ id, type, displayName }) => {
    const ext = vscode.extensions.getExtension(id);
    if (ext) {
      agents.push({
        id,
        displayName: ext.packageJSON.displayName || displayName,
        type,
        role: roleFor(type),
      });
    }
  });

  const hasGemini = antigravity || agents.some((a) => a.type === 'gemini');
  const hasKilo = agents.some((a) => a.type === 'kilo');
  const hasCline = agents.some((a) => a.type === 'cline');
  const trioReady = hasGemini && hasKilo && hasCline;

  let mode: SwarmMode = 'standalone';
  if (agents.length >= 3) mode = 'swarm';
  else if (agents.length >= 1) mode = 'duo';

  const state: SwarmState = {
    ide,
    agents,
    mode,
    agentCount: agents.length,
    hasGemini,
    hasKilo,
    hasCline,
    trioReady,
  };

  console.log(
    `[SupremeAI] Swarm: IDE=${ide}, agents=${agents.length}, mode=${mode}, ` +
      `trioReady=${trioReady} (gemini=${hasGemini}, kilo=${hasKilo}, cline=${hasCline})`
  );

  return state;
}

/** Backward-compatible: returns the list of detected agent display names (legacy API). */
export function detectOtherAiAgents(): string[] {
  return detectSwarmAgents().agents.map((a) => a.displayName);
}

/** Backward-compatible: returns the Trio-relevant (non-other) agents with role annotations. */
export function detectTrioPipelineAgents(): DetectedAgent[] {
  return detectSwarmAgents().agents.filter((a) => a.type !== 'other');
}

/** Notifies the user of the current swarm state. */
export function notifySwarmState(state: SwarmState): void {
  const msg = state.trioReady
    ? `SupremeAI Swarm ready: ${state.agents.map((a) => a.displayName).join(' + ')}`
    : `SupremeAI: ${state.agents.length} AI agent(s) detected on ${state.ide || 'VS Code'} - mode=${state.mode}`;
  vscode.window.showInformationMessage(msg);
}