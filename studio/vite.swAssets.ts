import fs from 'fs'
import path from 'path'

// #1761 — SW asset manifest (build truth, zero hash-shape guessing).
//
// Why this exists: studio/public/sw.js caches hashed build assets at runtime
// ("cache-as-you-fetch"), but its HASHED_ASSET_PATTERN accepted lowercase hex
// only, while Vite emits 8-char base64url hashes. Live probe 2026-10-28: the
// pattern matched 0/11 deployed assets (index-D_Trbe0G.js, vendor-events-
// Cp0iM0-l.js, ...), so the entire runtime-cache branch of the service worker
// was dead code and the warm path rode HTTP immutable cache alone — zero
// offline asset resilience.
//
// Rather than guessing hash shapes with a broader regex (which inevitably
// admits false positives on unhashed public files such as
// /manifest.webmanifest or /fonts/Inter-Variable.woff2), this plugin emits
// the authoritative list of hashed asset paths the build actually produced.
// sw.js prefers that manifest for its runtime-cache allowlist and keeps a
// corrected shape regex only as a fail-safe fallback for environments where
// the manifest is unreachable (dev servers emit unhashed assets and SW
// caching is not needed there anyway).
//
// Build-truth contract: Vite emits every hashed chunk/asset under the
// configured assetsDir ("assets" by default). Anything at dist root is either
// an unhashed public copy (favicon.ico, manifest.json, sw.js) or generated
// metadata (build-info.json, sw-assets.json). The contract is pinned by
// studio/src/swAssetContract.test.ts.

export function collectSwAssetPaths(bundle: Record<string, unknown>): string[] {
  return Object.keys(bundle)
    .filter((file) => file.startsWith('assets/'))
    .map((file) => `/${file}`)
    .sort()
}

export function swAssetManifestPlugin() {
  return {
    name: 'sw-asset-manifest-plugin',
    writeBundle(options: { dir?: string }, bundle: Record<string, unknown>) {
      if (process.env.NODE_ENV !== 'production') return
      const outDir = options?.dir || 'dist'
      const assets = collectSwAssetPaths(bundle)
      const payload = JSON.stringify({ generatedAt: new Date().toISOString(), assets }, null, 2)
      fs.writeFileSync(path.join(outDir, 'sw-assets.json'), payload)
      console.warn(`📋 SW asset manifest written to ${outDir}/sw-assets.json (${assets.length} hashed assets)`)
    },
  }
}
