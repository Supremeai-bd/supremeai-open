/**
 * AutonomousCodingAgent — OpenHands-type autonomous coding agent (thin client).
 *
 * থিন-ক্লায়েন্ট নীতি: এক্সটেনশন ভারী কিছু embedded করে না; বরং উপলব্ধ থাকলে একটি
 * self-hosted OpenHands agent-server REST API-কে রিমোট নিয়ন্ত্রণ করে।
 *
 * $0 ফিলোসফি: ডিফল্টে `enabled=false` → upstream active নয়; কোনো requestও যায় না।
 * শুধু user `supremeai.autonomousAgent.enabled=true` + `serverUrl` সেট করলে (এবং
 * নিজের/self-hosted server উপলব্ধ থাকলে) upstream REST flow চলে। না হলে graceful
 * fallback ("skipped + plan") — কোনো খরচ/ক্র্যাশ নেই।
 */

import * as vscode from 'vscode';
import axios from 'axios';

export interface AutonomousAgentConfig {
  enabled: boolean;
  serverUrl: string;
}

export interface AutonomousCodingResult {
  status: 'ok' | 'skipped' | 'error';
  engine: 'upstream' | 'fallback';
  sessionId?: string;
  result?: string;
  error?: string;
  note?: string;
}

export class AutonomousCodingAgent {
  private readonly enabled: boolean;
  private readonly serverUrl: string;

  constructor(config?: Partial<AutonomousAgentConfig>) {
    if (config) {
      this.enabled = config.enabled ?? false;
      this.serverUrl = (config.serverUrl || '').trim();
      return;
    }
    const cfg = vscode.workspace.getConfiguration('supremeai');
    this.enabled = cfg.get<boolean>('autonomousAgent.enabled') ?? false;
    this.serverUrl = (cfg.get<string>('autonomousAgent.serverUrl') || '').trim();
  }

  get active(): boolean {
    return this.enabled && this.serverUrl.length > 0;
  }

  async runTask(task: string, workspace?: string, maxSteps = 50): Promise<AutonomousCodingResult> {
    if (!task || !this.active) {
      return {
        status: 'skipped',
        engine: 'fallback',
        note:
          'Autonomous coding disabled or server URL not set. Enable ' +
          '"supremeai.autonomousAgent.enabled" and set "supremeai.autonomousAgent.serverUrl" to activate.',
      };
    }
    try {
      const sessionId = await this.createSession(workspace);
      await this.sendMessage(sessionId, task);
      const output = await this.collect(sessionId, maxSteps);
      return { status: 'ok', engine: 'upstream', sessionId, result: output || '(no output)' };
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return { status: 'error', engine: 'upstream', error: message };
    }
  }

  private async createSession(workspace?: string): Promise<string> {
    const resp = await axios.post(
      `${this.serverUrl}/api/sessions`,
      { headless: true, codebase: workspace || '', selected_agent: 'CodeActAgent' },
      { timeout: 30000 },
    );
    const id = resp?.data?.id;
    if (!id) throw new Error('Agent server did not return a session id');
    return String(id);
  }

  private async sendMessage(sessionId: string, task: string): Promise<void> {
    await axios.post(
      `${this.serverUrl}/api/sessions/${sessionId}/actions`,
      { action: 'message', args: { content: task } },
      { timeout: 30000 },
    );
  }

  private async collect(sessionId: string, maxSteps: number): Promise<string> {
    const last: string[] = [];
    for (let i = 0; i < maxSteps; i++) {
      const resp = await axios.get(`${this.serverUrl}/api/sessions/${sessionId}/events`, {
        timeout: 30000,
      });
      const events: unknown[] = Array.isArray(resp?.data) ? resp.data : [];
      for (const ev of events) {
        const content = this.extractText(ev);
        if (content) last.push(content);
      }
      if (events.some((ev) => this.isTerminal(ev))) break;
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
    return last.slice(-5).join(' ');
  }

  private extractText(ev: unknown): string {
    const content = (ev as { message?: { args?: { content?: unknown } } }).message?.args?.content;
    return typeof content === 'string' ? content : '';
  }

  private isTerminal(ev: unknown): boolean {
    const event = String((ev as { message?: { event?: unknown } }).message?.event || '').toLowerCase();
    return event === 'done' || event === 'error';
  }
}
