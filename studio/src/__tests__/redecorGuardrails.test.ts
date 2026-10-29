import { describe, it, expect, vi } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

// Redecoration guardrails (PR-1): freeze the misconfiguration classes that
// bit us before so the dashboard port cannot silently reintroduce them.
const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = path.join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name)) out.push(p);
  }
  return out;
}

describe('redecoration guardrails', () => {
  it('no firebase SDK import anywhere in studio/src (Zero-Firebase)', () => {
    const offenders = walk(SRC).filter((f) =>
      /from\s+['"](firebase|@firebase)\//.test(readFileSync(f, 'utf-8')),
    );
    expect(offenders).toEqual([]);
  });

  it('audioFx does not create an AudioContext at import time (autoplay policy)', async () => {
    const ctor = vi.fn();
    vi.stubGlobal('AudioContext', ctor);
    await import('../utils/audioFx');
    expect(ctor).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it('avatar defaults are a complete, serializable settings object', async () => {
    const { DEFAULT_AVATAR_SETTINGS } = await import('../types/avatar');
    expect(JSON.parse(JSON.stringify(DEFAULT_AVATAR_SETTINGS))).toEqual(DEFAULT_AVATAR_SETTINGS);
  });
});
