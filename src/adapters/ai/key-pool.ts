/**
 * AI key-pool tombstone (issue #643 — zero-credential control plane).
 *
 * বাংলা মন্তব্য: AIKeyPool আগে Gemini/Groq/OpenRouter/Mistral provider key-গুলো
 * round-robin ভাবে ধারণ করত। #643 অনুযায়ী control plane আর কোনো সরাসরি LLM
 * provider key ধারণ বা require করবে না — analysis বাইরের agent-caller context-এ
 * delegate করা হয়। ক্লাসটি back-compat import রক্ষার্থে রাখা হয়েছে, কিন্তু
 * সদা খালি: কোনো key সংরক্ষণ করা হয় না, কোনো key পড়া হয় না।
 */

export const KEY_POOL_RETIRED_NOTICE =
  "AIKeyPool is retired — the MCP Control Tower holds no direct LLM provider keys (#643).";

export class AIKeyPool {
  constructor(_keys?: string[]) {
    // ইচ্ছাকৃতভাবে constructor-এর argument উপেক্ষা করা হয় — কোনো key
    // মেমরিতে রাখা হয় না (#643 zero-credential contract)।
  }

  /** সর্বদা ০ — pool স্থায়ীভাবে খালি। */
  get length(): number {
    return 0;
  }

  /** সৎ ব্যর্থতা — কোনো key নেই (কখনোই থাকবে না, #643)। */
  public getNextKey(): string {
    throw new Error(KEY_POOL_RETIRED_NOTICE);
  }

  /** সৎ ব্যর্থতা — operation চালানোর জন্য কোনো key সরবরাহ করা হয় না। */
  public async execute<T>(_operation: (key: string) => Promise<T>, _isRateLimitError: (error: unknown) => boolean): Promise<T> {
    throw new Error(KEY_POOL_RETIRED_NOTICE);
  }
}
