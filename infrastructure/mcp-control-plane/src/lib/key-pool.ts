/**
 * Simple key pool for non-LLM provider adapters (Firecrawl scraping, Kaggle, etc.).
 * Supports round-robin rotation and automatic retry on rate-limit/quota errors.
 */

export class SimpleKeyPool {
  private keys: string[];
  private index = 0;

  constructor(keys?: string[]) {
    this.keys = (keys || []).map((k) => k.trim()).filter(Boolean);
  }

  get length(): number {
    return this.keys.length;
  }

  public getNextKey(): string {
    if (this.keys.length === 0) {
      throw new Error("No keys available in pool.");
    }
    const key = this.keys[this.index % this.keys.length];
    this.index++;
    return key;
  }

  public async execute<T>(
    operation: (key: string) => Promise<T>,
    isRateLimitError: (error: unknown) => boolean,
  ): Promise<T> {
    if (this.keys.length === 0) {
      throw new Error("No keys available in pool.");
    }
    let lastError: unknown;
    for (let i = 0; i < this.keys.length; i++) {
      const key = this.getNextKey();
      try {
        return await operation(key);
      } catch (err) {
        lastError = err;
        if (isRateLimitError(err) && i < this.keys.length - 1) {
          continue;
        }
        throw err;
      }
    }
    throw lastError;
  }
}
