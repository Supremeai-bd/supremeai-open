// ── Qdrant semantic cache (#1522 / Q1 — Redis command-burn reduction) ────────
// বাংলা মন্তব্য: একই রকম প্রশ্ন বারবার এলে প্রতিবার Redis-ভিত্তিক downstream
// পথ (session, rate-limit, dispatch state ইত্যাদি) বারবার কমান্ড খরচ করে —
// Upstash free tier-এর 500k সিলিং-এর প্রধান শত্রু এই পুনরাবৃত্তি। এই মডিউল
// top-20 প্রশ্ন-প্যাটার্নের উত্তর Qdrant-এ জমা রাখে; cosine-সদৃশ স্কোর থ্রেশহোল্ড
// ছাড়িয়ে গেলে সরাসরি cached উত্তর ফেরত — Redis কমান্ড শূন্য।
//
// Embedder honesty (U2 tiering — কোনো ভুয়া "semantic" দাবি নয়):
//   1. GEMINI_API_KEY থাকলে → Gemini text-embedding-004 (প্রকৃত semantic vector)।
//   2. না থাকলে → char-trigram lexical cosine fallback। এটি প্রকৃত embedding নয় —
//      কিন্তু "top-20 question patterns" বাস্তবে প্রায়-অভিন্ন স্ট্রিং হয়, তাই
//      পুনরাবৃত্ত-প্রশ্ন ধরার কাজটি করে; এবং প্রতিটি ফলাফলে `embedder` ফিল্ডে
//      সত্য পরিচয় বহন করে ("gemini" বনা "trigram-lexical-fallback")।
//
// Fail-open policy (AGENTS.md invariant #3 graceful degradation): Qdrant না
// চললে/না কনফিগার থাকলে প্রতিটি কল {hit:false, reason} দেয় — cache-এর ব্যর্থতা
// কখনো caller-এর মূল পথ ব্লক করে না, শুধু saving হারায়।

import { createHash } from "node:crypto";
import { env } from "./env.js";
import { httpRequest } from "./http.js";
import {
  qdrantEnsureCollection,
  qdrantSearch,
  qdrantUpsert,
} from "../adapters/qdrant/actions.js";

const DEFAULT_COLLECTION = "semantic_cache_v1";
const DEFAULT_HIT_THRESHOLD = 0.93;
const DEFAULT_MAX_ENTRIES = 20;
const DEFAULT_MAX_ANSWER_CHARS = 4000;
const TRIGRAM_DIM = 512;

export type CacheHit = {
  hit: boolean;
  score?: number;
  question?: string;
  answer?: string;
  embedder?: string;
  reason?: string;
};

export type CacheConfigStatus = {
  qdrantConfigured: boolean;
  embedder: "gemini" | "trigram-lexical-fallback";
  collection: string;
  hitThreshold: number;
  maxEntries: number;
  maxAnswerChars: number;
  topK: number;
};

function collection(): string {
  return process.env.SEMANTIC_CACHE_COLLECTION || DEFAULT_COLLECTION;
}

function hitThreshold(): number {
  const raw = Number(process.env.SEMANTIC_CACHE_HIT_THRESHOLD);
  return Number.isFinite(raw) && raw > 0 && raw <= 1 ? raw : DEFAULT_HIT_THRESHOLD;
}

function maxEntries(): number {
  const raw = Number(process.env.SEMANTIC_CACHE_MAX_ENTRIES);
  return Number.isFinite(raw) && raw > 0 ? Math.floor(raw) : DEFAULT_MAX_ENTRIES;
}

function maxAnswerChars(): number {
  const raw = Number(process.env.SEMANTIC_CACHE_MAX_ANSWER_CHARS);
  return Number.isFinite(raw) && raw > 0 ? Math.floor(raw) : DEFAULT_MAX_ANSWER_CHARS;
}

function topK(): number {
  return Math.max(3, Math.min(10, maxEntries()));
}

export function cacheConfigStatus(): CacheConfigStatus {
  return {
    qdrantConfigured: Boolean(env.qdrant.url),
    embedder: process.env.GEMINI_API_KEY ? "gemini" : "trigram-lexical-fallback",
    collection: collection(),
    hitThreshold: hitThreshold(),
    maxEntries: maxEntries(),
    maxAnswerChars: maxAnswerChars(),
    topK: topK(),
  };
}

// ── embedder tiering ──────────────────────────────────────────────────────────

function normalizeQuestion(text: string): string {
  return (text || "").toLowerCase().replace(/\s+/g, " ").trim();
}

/** FNV-1a → bucket index (deterministic, stdlib-free arithmetic). */
function fnv1a(str: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash >>> 0;
}

/** Char-trigram bag-of-words, L2-normalized. Lexical similarity, NOT semantics. */
function trigramVector(text: string): number[] {
  const padded = `  ${normalizeQuestion(text)}  `;
  const vec = new Array<number>(TRIGRAM_DIM).fill(0);
  for (let i = 0; i + 3 <= padded.length; i++) {
    vec[fnv1a(padded.slice(i, i + 3)) % TRIGRAM_DIM] += 1;
  }
  let norm = 0;
  for (const v of vec) norm += v * v;
  norm = Math.sqrt(norm);
  return norm > 0 ? vec.map((v) => v / norm) : vec;
}

async function geminiEmbed(text: string): Promise<number[]> {
  const key = process.env.GEMINI_API_KEY;
  const res = await httpRequest(
    `https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key=${key}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: {
        model: "models/text-embedding-004",
        content: { parts: [{ text }] },
      },
      timeoutMs: 15_000,
    },
  );
  const data = res.data as { embedding?: { values?: number[] } };
  const values = data?.embedding?.values;
  if (!res.ok || !Array.isArray(values) || values.length === 0) {
    throw new Error(`Gemini embedding failed (${res.status})`);
  }
  return values;
}

/** Embedder tier 1 = Gemini (semantic); tier 2 = trigram (lexical, labeled). */
async function embed(text: string): Promise<{ vector: number[]; embedder: "gemini" | "trigram-lexical-fallback" }> {
  if (process.env.GEMINI_API_KEY) {
    try {
      return { vector: await geminiEmbed(text), embedder: "gemini" };
    } catch {
      // Provider hiccup → fall through to the lexical fallback (never block).
    }
  }
  return { vector: trigramVector(text), embedder: "trigram-lexical-fallback" };
}

// ── Qdrant plumbing (ensure-once, count, prune-oldest) ────────────────────────

let ensuredDim = 0;

async function ensureCollection(dim: number): Promise<void> {
  if (ensuredDim === dim) return;
  await qdrantEnsureCollection(collection(), dim, "Cosine");
  ensuredDim = dim;
}

async function countPoints(): Promise<number> {
  const { url, apiKey } = { url: env.qdrant.url, apiKey: env.qdrant.apiKey || undefined };
  const res = await httpRequest(`${url}/collections/${collection()}/points/count`, {
    method: "POST",
    headers: apiKey ? { "api-key": apiKey, "Content-Type": "application/json" } : { "Content-Type": "application/json" },
    body: { exact: true },
    timeoutMs: 10_000,
  });
  const data = res.data as { count?: number };
  return res.ok && Number.isFinite(data?.count) ? Number(data.count) : 0;
}

async function deletePoints(ids: string[]): Promise<void> {
  if (ids.length === 0) return;
  const { url, apiKey } = { url: env.qdrant.url, apiKey: env.qdrant.apiKey || undefined };
  await httpRequest(`${url}/collections/${collection()}/points/delete?wait=true`, {
    method: "POST",
    headers: apiKey ? { "api-key": apiKey, "Content-Type": "application/json" } : { "Content-Type": "application/json" },
    body: { points: ids },
    timeoutMs: 10_000,
  });
}

/** Keep only the newest maxEntries points (oldest by payload.storedAt die). */
async function pruneToMax(): Promise<number> {
  const cap = maxEntries();
  const count = await countPoints();
  if (count <= cap) return 0;
  const { url, apiKey } = { url: env.qdrant.url, apiKey: env.qdrant.apiKey || undefined };
  const res = await httpRequest(`${url}/collections/${collection()}/points/scroll`, {
    method: "POST",
    headers: apiKey ? { "api-key": apiKey, "Content-Type": "application/json" } : { "Content-Type": "application/json" },
    body: { limit: 256, with_payload: true, with_vector: false },
    timeoutMs: 10_000,
  });
  const data = res.data as { points?: Array<{ id: string; payload?: Record<string, unknown> }> };
  const points = data?.points ?? [];
  if (points.length <= cap) return 0;
  const sorted = [...points].sort((a, b) =>
    String(a.payload?.storedAt ?? "").localeCompare(String(b.payload?.storedAt ?? "")),
  );
  const doomed = sorted.slice(0, points.length - cap).map((p) => String(p.id));
  await deletePoints(doomed);
  return doomed.length;
}

/** Deterministic UUID-shaped id from the normalized question — same question overwrites itself. */
function pointIdFor(question: string): string {
  const hex = createHash("sha256").update(normalizeQuestion(question), "utf8").digest("hex").slice(0, 32);
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20, 32)}`;
}

// ── public API ────────────────────────────────────────────────────────────────

export async function cacheLookup(question: string): Promise<CacheHit> {
  if (!env.qdrant.url) {
    return { hit: false, reason: "QDRANT_URL not configured — cache is dormant (fail-open)." };
  }
  const normalized = normalizeQuestion(question);
  if (!normalized) {
    return { hit: false, reason: "empty question" };
  }
  const { vector, embedder } = await embed(normalized);
  await ensureCollection(vector.length);
  const raw = await qdrantSearch(collection(), vector, topK());
  const points = Array.isArray((raw as { result?: unknown[] }).result)
    ? ((raw as { result: Array<{ score: number; payload?: Record<string, unknown> }> }).result)
    : [];
  if (points.length === 0) {
    return { hit: false, embedder, reason: "cache empty for this embedder space" };
  }
  const best = points[0];
  const threshold = hitThreshold();
  if (best.score >= threshold && typeof best.payload?.answer === "string") {
    return {
      hit: true,
      score: best.score,
      question: String(best.payload?.question ?? ""),
      answer: String(best.payload?.answer),
      embedder,
    };
  }
  return { hit: false, score: best.score, embedder, reason: `best score ${best.score.toFixed(4)} < threshold ${threshold}` };
}

export async function cacheStore(question: string, answer: string): Promise<{ stored: boolean; pruned: number; reason?: string }> {
  if (!env.qdrant.url) {
    return { stored: false, pruned: 0, reason: "QDRANT_URL not configured — cache is dormant (fail-open)." };
  }
  const normalized = normalizeQuestion(question);
  if (!normalized || !answer) {
    return { stored: false, pruned: 0, reason: "empty question or answer" };
  }
  const cappedAnswer = answer.slice(0, maxAnswerChars());
  const { vector, embedder } = await embed(normalized);
  await ensureCollection(vector.length);
  await qdrantUpsert(collection(), [
    {
      id: pointIdFor(normalized),
      vector,
      payload: {
        question: normalized,
        answer: cappedAnswer,
        embedder,
        storedAt: new Date().toISOString(),
      },
    },
  ]);
  const pruned = await pruneToMax();
  return { stored: true, pruned };
}
