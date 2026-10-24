/**
 * SuperAI Cost Optimizer Service (Vite-Compatible)
 * 
 * Replaces broken Next.js middleware with Vite-compatible solution.
 * Can be used as:
 * 1. Service worker for SPA
 * 2. Axios interceptor for API calls
 * 3. React Query configuration
 */

import { getCacheStats, resetCacheStats } from '../lib/cache.manager';

// ═══════════════════════════════════════════════════════════════
// CONFIGURATION
// ═══════════════════════════════════════════════════════════════

interface CostOptimizerConfig {
  enableResponseCache: boolean;
  enableRateLimiting: boolean;
  enableCompression: boolean;
  enableDeduplication: boolean;
  rateLimitRequests: number;
  rateLimitWindowMs: number;
  maxPayloadSize: number;
  cacheTTL: {
    static: number;
    api: number;
    ai: number;
  };
}

const DEFAULT_CONFIG: CostOptimizerConfig = {
  enableResponseCache: true,
  enableRateLimiting: true,
  enableCompression: true,
  enableDeduplication: true,
  rateLimitRequests: 10,
  rateLimitWindowMs: 60000,
  maxPayloadSize: 1024 * 1024, // 1MB
  cacheTTL: {
    static: 3600,    // 1 hour for static
    api: 300,      // 5 min for API
    ai: 60,        // 1 min for AI (cache less, fresher data)
  },
};

// ═══════════════════════════════════════════════════════════════
// RATE LIMITER (In-Memory with localStorage backup)
// ═══════════════════════════════════════════════════════════════

class RateLimiter {
  private requests: Map<string, number[]> = new Map();
  private config: CostOptimizerConfig;
  
  constructor(config: CostOptimizerConfig) {
    this.config = config;
    this._loadFromStorage();
  }
  
  checkLimit(identifier: string): { allowed: boolean; remaining: number; resetTime: Date } {
    const now = Date.now();
    const windowStart = now - this.config.rateLimitWindowMs;
    
    let timestamps = this.requests.get(identifier) || [];
    
    // Clean old entries outside window
    timestamps = timestamps.filter(t => t > windowStart);
    
    if (timestamps.length >= this.config.rateLimitRequests) {
      const oldestInWindow = timestamps[0];
      return {
        allowed: false,
        remaining: 0,
        resetTime: new Date(oldestInWindow + this.config.rateLimitWindowMs)
      };
    }
    
    // Add current request
    timestamps.push(now);
    this.requests.set(identifier, timestamps);
    this._persistToStorage();
    
    return {
      allowed: true,
      remaining: this.config.rateLimitRequests - timestamps.length - 1,
      resetTime: new Date(now + this.config.rateLimitWindowMs)
    };
  }
  
  reset(identifier?: string): void {
    if (identifier) {
      this.requests.delete(identifier);
    } else {
      this.requests.clear();
    }
    this._persistToStorage();
  }
  
  private _loadFromStorage(): void {
    try {
      const stored = localStorage.getItem('superai_rate_limits');
      if (stored) {
        const parsed = JSON.parse(stored);
        this.requests = new Map(Object.entries(parsed));
      }
    } catch {
      // Storage not available
    }
  }
  
  private _persistToStorage(): void {
    try {
      const obj: Record<string, number[]> = {};
      this.requests.forEach((value, key) => {
        obj[key] = value;
      });
      localStorage.setItem('superai_rate_limits', JSON.stringify(obj));
    } catch {
      // Storage not available or full
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// REQUEST DEDUPLICATOR
// ═══════════════════════════════════════════════════════════════

class RequestDeduplicator {
  private recentRequests: Map<string, { timestamp: number; response: unknown }> = new Map();
  private windowMs: number = 120000; // 2 minutes
  
  constructor(windowMs?: number) {
    if (windowMs) this.windowMs = windowMs;
  }
  
  getHash(data: string): string {
    let hash = 0;
    for (let i = 0; i < data.length; i++) {
      const char = data.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash |= 0;
    }
    return hash.toString();
  }
  
  check<T>(requestHash: string, fetchFn: () => Promise<T>): Promise<T> {
    const cached = this.recentRequests.get(requestHash);
    
    if (cached && Date.now() - cached.timestamp < this.windowMs) {
      return cached.response as Promise<T>;
    }
    
    return fetchFn().then(response => {
      // Cache successful responses
      this.recentRequests.set(requestHash, {
        timestamp: Date.now(),
        response
      });
      
      // Cleanup old entries periodically
      if (this.recentRequests.size > 200) {
        this._cleanup();
      }
      
      return response;
    });
  }
  
  private _cleanup(): void {
    const cutoff = Date.now() - this.windowMs * 2;
    for (const [key, value] of this.recentRequests.entries()) {
      if (value.timestamp < cutoff) {
        this.recentRequests.delete(key);
      }
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// MAIN COST OPTIMIZER SERVICE
// ═══════════════════════════════════════════════════════════════

export class CostOptimizerService {
  private config: CostOptimizerConfig;
  private rateLimiter: RateLimiter;
  private deduplicator: RequestDeduplicator;
  
  constructor(config: Partial<CostOptimizerConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.rateLimiter = new RateLimiter(this.config);
    this.deduplicator = new RequestDeduplicator();
  }
  
  // ═════════════════════════════════════════════════════════
  // PUBLIC METHODS
  // ═════════════════════════════════════════════════════════
  
  /**
   * Check if an API call should be allowed (rate limit check)
   */
  canMakeRequest(endpoint: string, userId?: string): { 
    allowed: boolean; 
    remaining: number; 
    retryAfter?: number;
  } {
    if (!this.config.enableRateLimiting) {
      return { allowed: true, remaining: Infinity };
    }
    
    const identifier = userId || endpoint;
    const result = this.rateLimiter.checkLimit(identifier);
    
    return {
      allowed: result.allowed,
      remaining: result.remaining,
      retryAfter: result.allowed ? undefined : 
        Math.ceil((result.resetTime.getTime() - Date.now()) / 1000)
    };
  }
  
  /**
   * Deduplicate a request if similar one was made recently
   */
  async deduplicateRequest<T>(
    requestData: string,
    fetchFn: () => Promise<T>
  ): Promise<T> {
    if (!this.config.enableDeduplication) {
      return fetchFn();
    }
    
    const hash = this.deduplicator.getHash(requestData);
    return this.deduplicator.check(hash, fetchFn);
  }
  
  /**
   * Validate payload size
   */
  validatePayloadSize(data: string | object): { valid: boolean; size: number; maxSize: number } {
    const size = typeof data === 'string' ? data.length : JSON.stringify(data).length;
    return {
      valid: size <= this.config.maxPayloadSize,
      size,
      maxSize: this.config.maxPayloadSize
    };
  }
  
  /**
   * Get optimal cache TTL for a given path/type
   */
  getCacheTTLForPath(path: string): number {
    if (path.includes('/api/ai/') || path.includes('/api/generate')) {
      return this.config.cacheTTL.ai;
    }
    if (path.startsWith('/api/')) {
      return this.config.cacheTTL.api;
    }
    return this.config.cacheTTL.static;
  }
  
  /**
   * Get full optimization report (for admin dashboard)
   */
  getOptimizationReport(): {
    rateLimits: unknown;
    cacheStats: ReturnType<typeof getCacheStats>;
    config: CostOptimizerConfig;
    savings: {
      estimatedRequestsSaved: number;
      estimatedCostSaved: number;
    };
  } {
    const cacheStats = getCacheStats();
    const hitRate = cacheStats.hits / (cacheStats.hits + cacheStats.misses) || 0;
    
    return {
      rateLimits: this.rateLimiter as unknown,
      cacheStats,
      config: this.config,
      savings: {
        estimatedRequestsSaved: cacheStats.hits,
        estimatedCostSaved: Math.round(hitRate * 0.02 * cacheStats.hits)  // $0.02 per saved API call
      }
    };
  }
  
  /**
   * Reset all optimization state (call monthly)
   */
  resetAll(): void {
    this.rateLimiter.reset();
    resetCacheStats();
  }
}

// ═══════════════════════════════════════════════════════════════
// SINGLETON EXPORT
// ═══════════════════════════════════════════════════════════════

let _instance: CostOptimizerService | null = null;

export function getCostOptimizer(config?: Partial<CostOptimizerConfig>): CostOptimizerService {
  if (!_instance) {
    _instance = new CostOptimizerService(config);
  }
  return _instance;
}

// Default export
export default CostOptimizerService;
