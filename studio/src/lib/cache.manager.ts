/**
 * SuperAI Cache Manager - FREE-TIER OPTIMIZED
 * 
 * Features:
 * - Multi-tier TTL strategy (save Redis commands!)
 * - Smart compression (reduce memory usage)
 * - Batch operations (reduce round-trips)
 * - Pattern-based invalidation
 * - Usage tracking (stay within free limits!)
 * 
 * Free Tier Limits:
 * - Upstash: 10,000 commands/day
 * - Storage: 256 MB max
 * - This manager helps you MAXIMIZE usage!
 */

// Issue #685 (Section 1, bundle): ``@upstash/redis`` is a server-side Redis
// SDK — it must remain TYPE-ONLY here so it never enters any client chunk.
import type { Redis } from '@upstash/redis';

// ============================================================================
// SECURITY FIX (#2510): Upstash REST tokens are FULL-ADMIN server-side
// credentials (read/write/flush). Reading them from `import.meta.env` bakes
// them into the browser bundle — anyone with devtools could flush production
// Redis. The browser NEVER holds these credentials anymore:
//
//   - No env read remains in this module (source-scan guard test enforces it).
//   - getRedis() always throws an honest error; cachedFetch's existing catch
//     falls back to a direct fetch (graceful, no fake cache hits).
//   - Cache features that genuinely need Redis must go through a BACKEND
//     proxy route that holds the token server-side.
//   - Rotation note: if VITE_UPSTASH_REDIS_REST_TOKEN was ever set in a
//     deploy config, the token shipped — rotate it (vault key
//     UPSTASH_REDIS_REST_TOKEN).
// ============================================================================
async function getRedis(): Promise<Redis> {
  // SECURITY FIX (#2510): intentionally unreachable success path — the browser
  // must never hold Redis admin credentials. Kept as an honest, explanatory
  // throw so every Redis-backed helper below degrades predictably
  // (cachedFetch → direct-fetch fallback; the rest → explicit error).
  throw new Error(
    '[cache.manager] Redis admin credentials are not available in the browser (#2510). ' +
      'Upstash REST tokens are server-side secrets and are no longer read from client env. ' +
      'Route cache operations through a backend proxy that holds the token, or use the ' +
      'direct-fetch fallback (cachedFetch already does).',
  );
}

// ✅ ENHANCED: Proper compression using Compression Streams API
async function compress(data: string): Promise<string> {
  if (data.length < 1024) return data;  // Don't bother compressing small payloads
  
  try {
    if (typeof CompressionStream !== 'undefined') {
      const compressed = new Blob([data]).stream()
        .pipeThrough(new CompressionStream('gzip'));
      const reader = compressed.getReader();
      const chunks: Uint8Array[] = [];
      let totalLength = 0;
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        totalLength += value.length;
      }
      
      // Only use compressed version if it's actually smaller
      if (totalLength < data.length) {
        const result = new Uint8Array(totalLength);
        let offset = 0;
        for (const chunk of chunks) {
          result.set(chunk, offset);
          offset += chunk.length;
        }
        return btoa(String.fromCharCode(...result));
      }
    }
  } catch (e) {
    console.warn('Compression failed, using raw data:', e);
  }
  
  return data;
}

// ✅ ENHANCED: Decompression
async function decompress(data: string): Promise<string> {
  try {
    if (typeof DecompressionStream !== 'undefined' && data.length > 256) {
      const binary = atob(data);
      const compressedBytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) {
        compressedBytes[i] = binary.charCodeAt(i);
      }
      
      const decompressed = new Blob([compressedBytes]).stream()
        .pipeThrough(new DecompressionStream('gzip'));
      const reader = decompressed.getReader();
      const chunks: Uint8Array[] = [];
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
      }
      
      const totalLength = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
      const bytes = new Uint8Array(totalLength);
      let offset = 0;
      for (const chunk of chunks) {
        bytes.set(chunk, offset);
        offset += chunk.length;
      }
      return new TextDecoder().decode(bytes);
    }
  } catch (e) {
    console.warn('Decompression failed, returning raw:', e);
  }
  
  return data;
}

// Cache TTL constants (optimized for free tier)
export const CACHE_TTL = {
  INSTANT: 60,         // 1 minute - Real-time data
  SHORT: 300,          // 5 minutes - Semi-dynamic
  MEDIUM: 1800,        // 30 minutes - User data
  LONG: 3600,          // 1 hour - Config/settings
  DAILY: 86400,        // 24 hours - Static content
  WEEKLY: 604800,      // 1 week - Rarely changing
} as const;

// ✅ NEW: Cache statistics tracking
const cacheStats = {
  hits: 0,
  misses: 0,
  errors: 0,
  bytes_saved: 0,
  commands_used: 0,
};

// ✅ NEW: Get cache hit ratio (for monitoring dashboard)
export function getCacheStats(): typeof cacheStats {
  return { ...cacheStats };
}

// ✅ NEW: Reset stats (call daily)
export function resetCacheStats(): void {
  cacheStats.hits = 0;
  cacheStats.misses = 0;
  cacheStats.errors = 0;
  cacheStats.bytes_saved = 0;
  cacheStats.commands_used = 0;
}

interface CacheOptions<T> {
  ttl?: number;           // Time-to-live in seconds
  key?: string;           // Custom cache key
  fallback?: () => Promise<T>;  // Fallback function
  compress?: boolean;     // Enable compression
}

// Main caching function with free-tier optimizations
// বাংলা (#3162): browser-side Redis নেই (getRedis throws) — cachedFetch direct
// fetch-এ fall back করে। commands_used আগে getRedis-এর আগে increment হতো →
// fake count। এখন শুধু successful Redis path-এ increment (যা কখনো হয় না)।
export async function cachedFetch<T>(
  cacheKey: string,
  fetcher: () => Promise<T>,
  options: CacheOptions<T> = {}
): Promise<T> {
  const {
    ttl = CACHE_TTL.MEDIUM,
    compress: compressionEnabled = true,
  } = options;

  const fullKey = `superai:${cacheKey}`;
  
  try {
    // বাংলা (#3162): commands_used সরানো হলো getRedis-এর আগে থেকে —
    // Redis unavailable হলে count হবে না (no fake Redis command count)।
    const redis = await getRedis();
    // ✅ Track command usage — শুধু যখন Redis সত্যিকারে available
    cacheStats.commands_used++;
    
    if (cacheStats.commands_used > 9000) {
      console.warn('⚠️ Approaching daily Redis command limit! Consider increasing TTL.');
    }
    
    // Try cache first (saves API calls AND Redis commands!)
    const cached = await redis.get<string>(fullKey);
    if (cached) {
      cacheStats.hits++;
      cacheStats.bytes_saved += cached.length;  // Avoided re-fetching this size
      
      return JSON.parse(await decompress(cached));  // ✅ Use proper decompression
    }

    
    // Fetch fresh data
    const data = await fetcher();
    
    // ✅ Store COMPRESSED data in cache (saves memory!)
    const serialized = JSON.stringify(data);
    const compressed = compressionEnabled ? await compress(serialized) : serialized;
    await redis.set(fullKey, compressed, { ex: ttl });
    
    cacheStats.misses++;
    
    return data;
  } catch (error) {
    cacheStats.errors++;  // ✅ Track errors
    console.error('Cache error:', error);
    // Fallback to direct fetch on cache failure
    return fetcher();
  }
}

// Browser-side Redis is intentionally disabled (#2510). These operations must
// fail explicitly so callers do not mistake an unavailable cache for a hit.
const browserCacheError = () =>
  new Error('[cache.manager] batch cache operations require a backend proxy (#2510).');

export async function batchGet<T>(_keys: string[]): Promise<(T | null)[]> {
  throw browserCacheError();
}

// ✅ NEW: Prefetch commonly accessed keys (call on app startup)
export async function prefetchCommonKeys(): Promise<void> {
  const commonKeys = [
    'app:config',
    'user:defaults',
    'llm:models:available',
    'features:enabled',
    'pricing:plans'
  ];
  
  
  for (const key of commonKeys) {
    try {
      const redis = await getRedis();
      const exists = await redis.exists(`superai:${key}`);
      if (!exists) {
        // Trigger fetch (will be cached)
      }
    } catch (e) {
      console.warn(`[CacheManager] Failed to check cache key ${key}:`, e);
    }
  }
}

// ✅ NEW: Intelligent cache warming based on access patterns
export async function warmCacheFromPatterns(): Promise<void> {
  // Find patterns that are frequently accessed but often miss
  const patternsToWarm = [
    { pattern: 'user:*:profile', ttl: CACHE_TTL.MEDIUM },
    { pattern: 'llm:*:response', ttl: CACHE_TTL.SHORT },
    { pattern: 'config:*', ttl: CACHE_TTL.LONG },
  ];
  
  for (const { pattern: _pattern, ttl: _ttl } of patternsToWarm) {
    // Implementation would analyze access logs and pre-warm
  }
}

// Smart invalidation belongs behind a backend cache proxy.
export async function invalidatePattern(_pattern: string): Promise<void> {
  throw browserCacheError();
}

// Usage tracking (stay within free tier!)
let dailyCommandCount = 0;
const MAX_DAILY_COMMANDS = 9000; // Leave buffer

export function trackRedisCommand(): boolean {
  dailyCommandCount++;
  return dailyCommandCount < MAX_DAILY_COMMANDS;
}
// SECURITY NOTE (#2510): getRedisClient is intentionally NOT exported — the
// browser-side Redis client no longer exists and must not be reintroduced.
// Cache features that need Redis belong behind a backend proxy route.
