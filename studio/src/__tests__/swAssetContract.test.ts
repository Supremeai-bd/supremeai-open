import { describe, it, expect } from 'vitest';
import { readFileSync, mkdtempSync } from 'fs';
import { tmpdir } from 'os';
import path from 'path';
import { fileURLToPath } from 'url';
import { collectSwAssetPaths, swAssetManifestPlugin } from '../../vite.swAssets';

// #1761 contract: the service worker's runtime asset caching must actually
// match the assets Vite emits. Two layers are pinned here:
//  1. public/sw.js — corrected HASHED_ASSET_PATTERN (base64url shape) matches
//     the live-deployed hashed assets and still rejects unhashed public files;
//     the sw-assets.json allowlist is loaded at install (build truth).
//  2. vite.swAssets.ts — the build emits sw-assets.json listing exactly the
//     hashed assets produced by the build (assets/ dir contract).

const swSource = readFileSync(
  path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../public/sw.js'),
  'utf-8',
);

function extractHashedAssetPattern(source: string): RegExp {
  const literal = source.match(/const HASHED_ASSET_PATTERN = (\/[^;\n]+\/[a-z]*);/);
  expect(literal, 'HASHED_ASSET_PATTERN literal not found in public/sw.js').toBeTruthy();
  const parts = literal![1].match(/^\/(.+)\/([a-z]*)$/)!;
  return new RegExp(parts[1], parts[2]);
}

// Live-deployed hashed assets probed on https://supremeai-studio.vercel.app
// on 2026-10-28 (the old lowercase-hex pattern matched 0 of these 11 assets;
// these are the hashed subset).
const DEPLOYED_HASHED_ASSETS = [
  '/assets/index-D_Trbe0G.js',
  '/assets/index-8hG3W7sl.css',
  '/assets/vendor-charts-CTAtHotd.js',
  '/assets/vendor-events-Cp0iM0-l.js',
  '/assets/vendor-query-k_5jDZAe.js',
  '/assets/vendor-react-BYetfKtC.js',
  '/assets/vendor-ui-BHhQdjFB.js',
];

// Same-origin, unhashed public files that must never enter the SW asset cache
// (a stale copy would survive deploys — the contract is fingerprinted-only).
const UNHASHED_PUBLIC_FILES = [
  '/logo.png',
  '/favicon.ico',
  '/favicon.svg',
  '/manifest.json',
  '/manifest.webmanifest',
  '/robots.txt',
  '/index.html',
];

describe('#1761 sw.js hashed-asset shape fallback', () => {
  const pattern = extractHashedAssetPattern(swSource);

  it('matches every live-deployed Vite hashed asset (base64url hash shape)', () => {
    for (const asset of DEPLOYED_HASHED_ASSETS) {
      expect(pattern.test(asset), `pattern must match ${asset}`).toBe(true);
    }
  });

  it('rejects unhashed public root files (no hashed segment before extension)', () => {
    for (const asset of UNHASHED_PUBLIC_FILES) {
      expect(pattern.test(asset), `pattern must reject ${asset}`).toBe(false);
    }
  });

  it('loads the build-truth allowlist at install (sw-assets.json)', () => {
    expect(swSource).toContain('/sw-assets.json');
    expect(swSource).toContain('loadAssetAllowlist');
  });

  it('bumps the cache namespace so the behavior change gets a fresh cache', () => {
    expect(swSource).toContain("CACHE_NAME = 'supremeai-pwa-cache-v5'");
  });
});

describe('#1761 vite.swAssets build-truth manifest', () => {
  it('collectSwAssetPaths lists exactly the hashed assets/ dir entries, sorted, root-anchored', () => {
    const bundle = {
      'assets/index-D_Trbe0G.js': {},
      'assets/index-8hG3W7sl.css': {},
      'assets/chunks/AdminShell-Cf3aB9xY.js': {},
      'index.html': {},
      'favicon.ico': {},
      'manifest.json': {},
      'build-info.json': {},
      'sw-assets.json': {},
    };
    expect(collectSwAssetPaths(bundle)).toEqual([
      '/assets/chunks/AdminShell-Cf3aB9xY.js',
      '/assets/index-8hG3W7sl.css',
      '/assets/index-D_Trbe0G.js',
    ]);
  });

  it('collectSwAssetPaths returns [] for a bundle with no hashed assets', () => {
    expect(collectSwAssetPaths({ 'index.html': {}, 'favicon.ico': {} })).toEqual([]);
  });

  it('writeBundle emits sw-assets.json with the hashed assets in production', () => {
    const dir = mkdtempSync(path.join(tmpdir(), 'sw-manifest-test-'));
    const prevNodeEnv = process.env.NODE_ENV;
    process.env.NODE_ENV = 'production';
    try {
      const plugin = swAssetManifestPlugin() as {
        writeBundle: (options: { dir?: string }, bundle: Record<string, unknown>) => void;
      };
      plugin.writeBundle({ dir }, { 'assets/index-abc123XY.js': {} });
      const written = JSON.parse(readFileSync(path.join(dir, 'sw-assets.json'), 'utf-8'));
      expect(written.assets).toEqual(['/assets/index-abc123XY.js']);
      expect(typeof written.generatedAt).toBe('string');
    } finally {
      process.env.NODE_ENV = prevNodeEnv;
    }
  });

  it('writeBundle is a no-op outside production (dev emits no manifest)', () => {
    const dir = mkdtempSync(path.join(tmpdir(), 'sw-manifest-test-'));
    const prevNodeEnv = process.env.NODE_ENV;
    process.env.NODE_ENV = 'test';
    try {
      const plugin = swAssetManifestPlugin() as {
        writeBundle: (options: { dir?: string }, bundle: Record<string, unknown>) => void;
      };
      plugin.writeBundle({ dir }, { 'assets/index-abc123XY.js': {} });
      expect(() => readFileSync(path.join(dir, 'sw-assets.json'))).toThrow();
    } finally {
      process.env.NODE_ENV = prevNodeEnv;
    }
  });
});
