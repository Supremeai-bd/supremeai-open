import { describe, it, expect } from 'vitest';
import { BUNDLED_PLUGINS, looksLikePlaintextSecret } from './marketplaceService';

// #1523 — bundled snapshot mirrors the control-plane catalog and the
// zero-plaintext invariant locally (fail before any network call).

describe('marketplaceService bundled catalog', () => {
  it('mirrors the Phase-1 seed: 5 providers, hosted templates only where official', () => {
    expect(BUNDLED_PLUGINS.map((p) => p.pluginId)).toEqual([
      'github',
      'telegram',
      'web-search',
      'google-drive',
      'notion',
    ]);
    expect(BUNDLED_PLUGINS.find((p) => p.pluginId === 'github')?.endpointTemplate).toBe(
      'https://api.githubcopilot.com/mcp/',
    );
    expect(BUNDLED_PLUGINS.find((p) => p.pluginId === 'notion')?.endpointTemplate).toBe(
      'https://mcp.notion.com/mcp',
    );
    for (const id of ['telegram', 'web-search', 'google-drive']) {
      expect(BUNDLED_PLUGINS.find((p) => p.pluginId === id)?.endpointTemplate).toBeNull();
    }
  });

  it('keeps the zero-plaintext invariant: secret-class fields, no live-token labels', () => {
    for (const plugin of BUNDLED_PLUGINS) {
      expect(plugin.trustLevel).toBe('untrusted');
      for (const field of plugin.credentialFields) {
        expect(field.secret).toBe(true);
        expect(field.required).toBe(true);
        expect(looksLikePlaintextSecret(field.label)).toBe(false);
      }
    }
  });
});

describe('looksLikePlaintextSecret (client-side guard mirror)', () => {
  it('accepts vault references and ordinary strings', () => {
    expect(looksLikePlaintextSecret('vault:github-token')).toBe(false);
    expect(looksLikePlaintextSecret('vault:team/bot-token')).toBe(false);
    expect(looksLikePlaintextSecret('my-cstored-ref')).toBe(false);
  });

  it('rejects live-token-shaped values across the secret-scan families', () => {
    expect(looksLikePlaintextSecret('ghp_Abc123def')).toBe(true);
    expect(looksLikePlaintextSecret('ghs_Abc123def')).toBe(true);
    expect(looksLikePlaintextSecret('sk-proj-abc123')).toBe(true);
    expect(looksLikePlaintextSecret('xoxb-123456')).toBe(true);
    expect(looksLikePlaintextSecret('AKIAIOSFODNN7')).toBe(true);
    expect(looksLikePlaintextSecret('AIzaSyA-abc')).toBe(true);
  });
});
