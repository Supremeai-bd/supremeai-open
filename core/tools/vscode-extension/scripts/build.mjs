/**
 * Custom esbuild script for SupremeAI VS Code extension.
 * Handles pnpm workspace symlink resolution correctly.
 */
import { build } from 'esbuild';
import { createRequire } from 'module';
import { fileURLToPath } from 'url';
import path from 'path';
import fs from 'fs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const extRoot = path.join(__dirname, '..');

// Find openai's real path by resolving from extension's node_modules
function findOpenAI() {
  // Check local node_modules first
  const localPath = path.join(extRoot, 'node_modules', 'openai');
  if (fs.existsSync(path.join(localPath, 'index.js')) || fs.existsSync(path.join(localPath, 'src'))) {
    return localPath;
  }
  // Try resolving the package.json of openai
  const localPkgPath = path.join(localPath, 'package.json');
  if (fs.existsSync(localPkgPath)) {
    return localPath;
  }
  // Traverse pnpm store
  const pnpmStore = path.join(extRoot, '..', '..', 'node_modules', '.pnpm');
  if (fs.existsSync(pnpmStore)) {
    const entries = fs.readdirSync(pnpmStore);
    const openaiEntry = entries.find(e => e.startsWith('openai@'));
    if (openaiEntry) {
      return path.join(pnpmStore, openaiEntry, 'node_modules', 'openai');
    }
  }
  return null;
}

const openaiPath = findOpenAI();
const alias = {};
if (openaiPath) {
  console.log(`✅ Resolved openai → ${openaiPath}`);
  alias['openai'] = openaiPath;
} else {
  console.warn('⚠️  openai not found, marking as external');
}

const result = await build({
  entryPoints: [path.join(extRoot, 'src', 'extension.ts')],
  bundle: true,
  outfile: path.join(extRoot, 'out', 'extension.js'),
  external: ['vscode', ...(openaiPath ? [] : ['openai'])],
  format: 'cjs',
  platform: 'node',
  minify: true,
  logLevel: 'warning',
  alias,
}).catch(err => {
  console.error('Build failed:', err.message);
  process.exit(1);
});

console.log('✅ Extension built successfully → out/extension.js');
