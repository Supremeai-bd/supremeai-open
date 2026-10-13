export class AIKeyPool {
  private keys: string[];
  private currentIndex: number = 0;

  constructor(keys: string[]) {
    this.keys = keys.filter((k) => k.trim().length > 0);
  }

  get length(): number {
    return this.keys.length;
  }

  /**
   * Get the next key in the pool (round-robin).
   */
  public getNextKey(): string {
    if (this.keys.length === 0) {
      throw new Error("No keys available in the pool");
    }
    const key = this.keys[this.currentIndex];
    this.currentIndex = (this.currentIndex + 1) % this.keys.length;
    return key;
  }

  /**
   * Execute a function with a key, falling back to the next key if a rate limit occurs.
   * By default, it will retry up to the number of keys in the pool.
   */
  public async execute<T>(
    operation: (key: string) => Promise<T>,
    isRateLimitError: (error: any) => boolean
  ): Promise<T> {
    if (this.keys.length === 0) {
      throw new Error("No keys available in the pool");
    }

    let attempts = 0;
    const maxAttempts = this.keys.length;
    let lastError: any;

    while (attempts < maxAttempts) {
      const key = this.getNextKey();
      try {
        return await operation(key);
      } catch (err) {
        lastError = err;
        if (isRateLimitError(err)) {
          console.warn(`[AIKeyPool] Rate limit hit on key. Trying next... (${attempts + 1}/${maxAttempts})`);
          attempts++;
        } else {
          // If it's not a rate limit error, don't fallback, just throw
          throw err;
        }
      }
    }

    throw new Error(`All keys in the pool are rate-limited. Last error: ${lastError?.message}`);
  }
}
