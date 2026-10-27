/**
 * Persistent cooldown ledger — P0 #1360 deliverable C.
 *
 * বাংলা মন্তব্য: `redis_chain.ts`-এর quota cooldown registry এখন পর্যন্ত
 * শুধু in-memory — tower process রিস্টার্ট/রিডিপ্লয় হলে primary/secondary-র
 * কোটা-মৃত্যু ভুলে যায়, আর সদ্য-জন্ম নেওয়া process হারিয়ে যাওয়া কোটা আবার
 * খরচ করে বসে (prICY error body না দেখা পর্যন্ত — প্রতিটি চেষ্টাই বৃথা
 * কমান্ড)। এই ledger cooldown stamp + usage proof ছোট একটি local JSON
 * ফাইলে লেখে; প্রসেস ফিরে এলে সেগুলো ফিরে পায় — একটিও বাড়তি Redis কমান্ড
 * খরচ না করে (zero Redis commands by design)।
 *
 * Opt-in by env: REDIS_COOLDOWN_LEDGER_PATH সেট থাকলেই persistence সক্রিয়।
 * আনসেট হলে আচরণ আগের মতোই byte-identical (in-memory only) — existing test
 * chains ও বিদ্যমান ডেপ্লয়মেন্ট অপরিবর্তিত। Render-এ এক লাইনের env যোগ করলেই
 * সক্রিয় (deployment step documented in the PR + capacity-model doc)।
 *
 * Honest limitation (documented, not hidden): /tmp-জাতীয় local ফাইল একই
 * instance-এর restart/redeploy সারভাইভ করে; পুরো instance recycle (নতুন
 * container) হলে ফাইলও যায় — কোটা-মৃত অ্যাকাউন্টে ফিরে গিয়ে একটি probe
 * কমান্ড খরচ হতে পারে, তার পরেই আবার stamp। Redis-এ স্বয়ং ledger রাখা
 * circular (মৃত অ্যাকাউন্ট নিজের মৃত্যু রেকর্ড করতে পারে না) — তাই এটিই
 * সর্বোচ্চ সততার সীমা।
 *
 * Safety contract:
 *  - Atomic writes (tmp + rename) — torn files impossible.
 *  - Corrupt/unreadable file → loud warn + fail-open (in-memory as before).
 *  - Load validates every stamp: future-dated AND window-current AND
 *    usage ≥ soft threshold (#1345 invariant) — else dropped at load.
 *  - Only chain labels known at load time are restored.
 */

import { existsSync, mkdirSync, readFileSync, renameSync, unlinkSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

export type LedgerEntry = {
  cooldownUntilMs: number;
  usage: { count: number; windowStartMs: number };
  stampedAtMs: number;
};

export type LedgerFile = {
  version: 1;
  entries: Record<string, LedgerEntry>;
};

export function cooldownLedgerPath(): string | null {
  const p = process.env.REDIS_COOLDOWN_LEDGER_PATH;
  return p && p.trim() !== "" ? p.trim() : null;
}

export function isCooldownLedgerEnabled(): boolean {
  return cooldownLedgerPath() !== null;
}

function emptyLedger(): LedgerFile {
  return { version: 1, entries: {} };
}

/** Loads the raw ledger file; returns null when disabled/absent, {} on corrupt. */
export function readLedgerFile(): LedgerFile | null {
  const path = cooldownLedgerPath();
  if (!path) return null;
  try {
    if (!existsSync(path)) return emptyLedger();
    const raw = readFileSync(path, "utf8");
    const parsed = JSON.parse(raw) as LedgerFile;
    if (!parsed || parsed.version !== 1 || typeof parsed.entries !== "object" || parsed.entries === null) {
      console.warn(`[cooldown-ledger] Unrecognized ledger shape at ${path} — ignoring (fail-open).`);
      return emptyLedger();
    }
    return parsed;
  } catch (err) {
    console.warn(
      `[cooldown-ledger] Failed to read ledger at ${path}: ${(err as Error).message} — continuing in-memory (fail-open).`,
    );
    return emptyLedger();
  }
}

/** Writes the full ledger atomically (tmp + rename). Never throws. */
export function writeLedgerFile(file: LedgerFile): void {
  const path = cooldownLedgerPath();
  if (!path) return;
  try {
    const dir = dirname(path);
    if (dir && dir !== "." && !existsSync(dir)) mkdirSync(dir, { recursive: true });
    const tmp = `${path}.tmp-${process.pid}-${Date.now()}`;
    writeFileSync(tmp, JSON.stringify(file), "utf8");
    renameSync(tmp, path);
  } catch (err) {
    console.warn(
      `[cooldown-ledger] Failed to persist ledger at ${path}: ${(err as Error).message} — continuing in-memory (fail-open).`,
    );
  }
}

/**
 * Upserts one account's stamp into the ledger (called by redis_chain AFTER the
 * in-memory registry is updated — the ledger mirrors memory, never leads it).
 */
export function persistCooldownStamp(
  label: string,
  cooldownUntilMs: number,
  usage: { count: number; windowStartMs: number },
  nowMs: number = Date.now(),
): void {
  if (!isCooldownLedgerEnabled()) return;
  const file = readLedgerFile() ?? emptyLedger();
  file.entries[label] = { cooldownUntilMs, usage, stampedAtMs: nowMs };
  writeLedgerFile(file);
}

/** Removes one account's stamp (recovery probe / self-heal / expiry). */
export function persistCooldownClear(label: string): void {
  if (!isCooldownLedgerEnabled()) return;
  const file = readLedgerFile() ?? emptyLedger();
  if (!(label in file.entries)) return;
  delete file.entries[label];
  writeLedgerFile(file);
}

/**
 * Validated hydration: returns only stamps worth restoring — future-dated,
 * usage window still current, usage ≥ soft threshold (the #1345 invariant the
 * registry would otherwise self-heal at first observation), and label present
 * in the caller-provided chain-label allowlist.
 */
export function validLedgerStamps(
  chainLabels: readonly string[],
  softThreshold: number,
  currentWindowStartMs: number,
  nowMs: number = Date.now(),
): Map<string, LedgerEntry> {
  const file = readLedgerFile();
  const out = new Map<string, LedgerEntry>();
  if (!file) return out;
  for (const [label, entry] of Object.entries(file.entries)) {
    if (!chainLabels.includes(label)) continue;
    if (!entry || typeof entry.cooldownUntilMs !== "number") continue;
    if (nowMs >= entry.cooldownUntilMs) continue; // expired — do not resurrect
    if (!entry.usage || typeof entry.usage.count !== "number") continue;
    if (entry.usage.windowStartMs !== currentWindowStartMs) continue; // stale window
    if (entry.usage.count < softThreshold) {
      console.warn(
        `[cooldown-ledger] Dropping stamp for "${label}": usage ${entry.usage.count} < soft threshold ` +
          `${softThreshold} (#1345 mis-stamp guard) — slot returns to rotation.`,
      );
      continue;
    }
    out.set(label, entry);
  }
  return out;
}

/** Test hook — removes the ledger file (memory-side state is owned by redis_chain). */
export function deleteCooldownLedgerFile(): void {
  const path = cooldownLedgerPath();
  if (!path) return;
  try {
    if (existsSync(path)) unlinkSync(path);
  } catch {
    // best-effort cleanup only
  }
}
