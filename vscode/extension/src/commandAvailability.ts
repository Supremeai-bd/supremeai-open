/**
 * vscode/extension/src/commandAvailability.ts — Runtime command discovery (Way 25).
 *
 * বাংলা: third-party command id ব্যবহারের আগে `vscode.commands.getCommands`
 * দিয়ে availability যাচাই + না পেলে graceful fallback notification (plan
 * Way 25) — ডেড কমান্ডে hard crash নয়।
 *
 * Usage (see INTEGRATION.diff for extension.ts):
 *   const ok = await ensureCommandAvailable('supremeai.chat.focus');
 *   if (ok) await vscode.commands.executeCommand('supremeai.chat.focus');
 */

import * as vscode from 'vscode';

/** Cache of the command list (refreshed at most once per activation window). */
let cachedCommands: Set<string> | null = null;

export async function refreshCommandCache(): Promise<Set<string>> {
  const all = await vscode.commands.getCommands(true);
  cachedCommands = new Set(all);
  return cachedCommands;
}

export function isCommandCached(id: string): boolean {
  return cachedCommands?.has(id) ?? false;
}

/**
 * Ensure a command exists before executing it.
 * - Fresh cache on first call per session (cheap; one getCommands round-trip).
 * - Optional `fallback` notification with an actionable "Reload" button
 *   (the standard cure for a stale extension host).
 * Returns true when the command was available.
 */
export async function ensureCommandAvailable(
  commandId: string,
  opts: { notifyOnMissing?: boolean; source?: string } = {},
): Promise<boolean> {
  if (!cachedCommands) {
    try {
      await refreshCommandCache();
    } catch {
      cachedCommands = null; // getCommands failure → treat as unknown
    }
  }

  if (cachedCommands?.has(commandId)) return true;

  // One re-check without cache before declaring absence (handles fresh installs).
  try {
    const fresh = await vscode.commands.getCommands(true);
    cachedCommands = new Set(fresh);
    if (cachedCommands.has(commandId)) return true;
  } catch {
    /* fall through to the missing path */
  }

  if (opts.notifyOnMissing !== false) {
    const source = opts.source ?? 'SupremeAI';
    vscode.window
      .showWarningMessage(
        `${source}: command "${commandId}" is not available yet. Reload the window to activate it.`,
        'Reload Window',
      )
      .then((choice) => {
        if (choice === 'Reload Window') {
          void vscode.commands.executeCommand('workbench.action.reloadWindow');
        }
      });
  }
  return false;
}

/** Test hook: reset the module-level cache (unit tests only). */
export function _resetCommandCacheForTests(): void {
  cachedCommands = null;
}
